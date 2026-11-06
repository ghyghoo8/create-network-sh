"""Outcome checks for bounded retries, using no SSH processes or network."""
from copy import deepcopy
import hashlib
import importlib.util
import json
from pathlib import Path
import unittest
from uuid import UUID


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("hindsight_adapter_under_test", ROOT / "adapter.py")
adapter = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(adapter)
CATALOG = json.loads((ROOT / "catalog.json").read_bytes())
BANK = "cf-fe-herdr"
OPERATION = "391becaf-e6ec-407c-9123-df4b49c1ca54"


class FakeClock:
    def __init__(self):
        self.now = 0.0
        self.sleeps = []

    def __call__(self):
        return self.now

    async def sleep(self, seconds):
        self.sleeps.append(seconds)
        self.now += seconds


class FakeTransport:
    def __init__(self, clock, steps):
        self.clock = clock
        self.steps = list(steps)
        self.calls = []

    async def call(self, protocol, tool, arguments, timeout, trace):
        self.calls.append({"protocol": protocol, "tool": tool, "arguments": deepcopy(arguments),
                           "timeout": timeout, "started": self.clock()})
        if not self.steps:
            raise AssertionError("Unexpected extra upstream call")
        step = self.steps.pop(0)
        elapsed = step.get("elapsed", 0)
        self.clock.now += timeout if elapsed == "timeout" else elapsed
        if "mutate" in step:
            step["mutate"](arguments)
        if "error" in step:
            raise step["error"]
        result = step["result"]
        return deepcopy(result(arguments) if callable(result) else result)


class GatewayTests(unittest.IsolatedAsyncioTestCase):
    def gateway(self, steps):
        clock = FakeClock()
        transport = FakeTransport(clock, steps)
        gateway = adapter.Gateway(transport, CATALOG, clock=clock, sleep=clock.sleep, jitter=lambda: 3.0)
        return gateway, transport, clock

    @staticmethod
    def recall_args():
        return {"bank_id": BANK, "query": "original project context"}

    @staticmethod
    def retain_args(*, operation=OPERATION):
        result = {"bank_id": BANK, "document_id": "issue13-source-event-1", "content": "original Unicode 内容",
                  "metadata": {"source": "issue13", "original_sha256": "f" * 64}}
        if operation is not None:
            result["operation_id"] = operation
        return result

    @staticmethod
    def meta(result):
        return result["_meta"]["hindsight_gateway"]

    async def invoke(self, gateway, tool="recall", arguments=None, **options):
        return await gateway.invoke(tool, self.recall_args() if arguments is None else arguments,
                                    allowed_banks={BANK}, **options)

    async def test_invalid_or_unauthorized_bank_never_connects(self):
        for bank in ("", " ", "default", "DEFAULT", " " + BANK, BANK + " ", "foreign-bank", None, 17):
            with self.subTest(bank=bank):
                gateway, transport, _ = self.gateway([])
                with self.assertRaises((ValueError, PermissionError)):
                    await self.invoke(gateway, arguments={"bank_id": bank, "query": "q"})
                self.assertEqual(transport.calls, [])

    async def test_all_project_banks_allows_existing_and_future_bank_names(self):
        for bank in ('existing-project', 'future-project'):
            with self.subTest(bank=bank):
                gateway, transport, _ = self.gateway([
                    {'result': adapter.result_body({'bank_id': bank})}])
                result = await self.invoke(gateway, arguments={'bank_id': bank, 'query': 'q'},
                                           all_project_banks=True)
                self.assertEqual(adapter.native_body(result)['bank_id'], bank)
                self.assertEqual(transport.calls[0]['arguments']['bank_id'], bank)

    async def test_all_project_banks_still_rejects_default_and_invalid_ids(self):
        for bank in ('', ' ', 'default', 'DEFAULT', ' default', BANK+' ', None, 17):
            with self.subTest(bank=bank):
                gateway, transport, _ = self.gateway([])
                with self.assertRaises((ValueError, PermissionError)):
                    await self.invoke(gateway, arguments={'bank_id': bank, 'query': 'q'},
                                      all_project_banks=True)
                self.assertEqual(transport.calls, [])

    async def test_false_or_wildcard_bank_entry_does_not_grant_all_projects(self):
        for allowed in ({BANK}, {'*'}):
            with self.subTest(allowed=allowed):
                gateway, transport, _ = self.gateway([])
                with self.assertRaises(PermissionError):
                    await gateway.invoke('recall', {'bank_id': 'future-project', 'query': 'q'},
                                         allowed_banks=allowed, all_project_banks=False)
                self.assertEqual(transport.calls, [])

    async def test_business_rpc_and_auth_errors_do_not_switch_protocol_or_retry(self):
        responses = (
            adapter.result_body({"state": "RESPONSE", "http_status": 401, "body": {"error": "unauthorized"}}, True),
            adapter.result_body({"state": "RESPONSE", "http_status": 403, "body": {"error": "forbidden"}}, True),
            adapter.result_body({"state": "RESPONSE", "http_status": 422, "body": {"error": "invalid bank"}}, True),
            adapter.result_body({"state": "RESPONSE", "rpc_error": {"code": -32602, "message": "Invalid arguments"}}, True),
            adapter.result_body({"error": "business refusal"}, True),
            adapter.result_body({"state": "RESPONSE", "http_status": 429, "response_headers": {"Retry-After": "60"}}, True),
            adapter.result_body({"state": "RESPONSE", "http_status": 503, "response_headers": {"Retry-After": "60"}}, True),
        )
        for response in responses:
            with self.subTest(response=response):
                gateway, transport, clock = self.gateway([{"result": response}])
                result = await self.invoke(gateway)
                self.assertTrue(result["isError"])
                self.assertEqual([(c["protocol"], c["tool"]) for c in transport.calls], [("mcp", "recall")])
                self.assertEqual(clock.sleeps, [])
        gateway, transport, _ = self.gateway([{"error": adapter.TransportFailure("AUTHENTICATION_FAILED", "ssh_connect_exec")}])
        self.assertTrue((await self.invoke(gateway))["isError"])
        self.assertEqual(len(transport.calls), 1)

    async def test_mcp_protocol_or_session_failure_reads_through_api_once(self):
        for kind in ("PROTOCOL", "SESSION"):
            with self.subTest(kind=kind):
                gateway, transport, _ = self.gateway([
                    {"error": adapter.TransportFailure(kind, "mcp_initialize")},
                    {"result": adapter.result_body({"state": "RESPONSE", "http_status": 200, "body": {"matches": ["original"]}})},
                ])
                result = await self.invoke(gateway)
                self.assertFalse(result["isError"])
                self.assertEqual([c["protocol"] for c in transport.calls], ["mcp", "api"])
                self.assertEqual(transport.calls[0]["arguments"], transport.calls[1]["arguments"])
                self.assertEqual(len(self.meta(result)["attempts"]), 2)

    async def test_network_or_timeout_rebuilds_same_mcp_without_api_switch(self):
        for kind in ("NETWORK", "TIMEOUT"):
            with self.subTest(kind=kind):
                gateway, transport, _ = self.gateway([
                    {"error": adapter.TransportFailure(kind, "ssh_connect_exec")},
                    {"result": adapter.result_body({"matches": []})},
                ])
                result = await self.invoke(gateway)
                self.assertEqual([c["protocol"] for c in transport.calls], ["mcp", "mcp"])
                self.assertIs(self.meta(result)["attempts"][1]["recreated_session"], True)

    async def test_two_failed_attempts_never_start_a_third_call(self):
        gateway, transport, _ = self.gateway([
            {"error": adapter.TransportFailure("NETWORK", "ssh_connect_exec")},
            {"error": adapter.TransportFailure("NETWORK", "ssh_connect_exec")},
            {"result": adapter.result_body({"should_not": "run"})},
        ])
        result = await self.invoke(gateway)
        self.assertTrue(result["isError"])
        self.assertEqual(len(transport.calls), 2)
        self.assertEqual(len(transport.steps), 1)

    async def test_retain_preserves_caller_uuid_and_freezes_payload_across_safe_fallback(self):
        original = self.retain_args()
        before = deepcopy(original)
        gateway, transport, _ = self.gateway([
            {"error": adapter.TransportFailure("PROTOCOL", "mcp_initialize", False),
             "mutate": lambda arguments: arguments.update(content="transport mutation must not leak")},
            {"result": lambda arguments: adapter.result_body({"state": "SUBMITTED", "body": {
                "operation_id": arguments["operation_id"]}})},
        ])
        result = await self.invoke(gateway, "retain", original)
        self.assertEqual(original, before)
        first, second = transport.calls
        self.assertEqual((first["protocol"], second["protocol"]), ("mcp", "api"))
        self.assertEqual(first["arguments"], second["arguments"])
        UUID(first["arguments"]["operation_id"])
        self.assertEqual(first["arguments"]["content"], before["content"])
        frozen = json.dumps(first["arguments"], sort_keys=True, ensure_ascii=False, allow_nan=False)
        self.assertEqual(self.meta(result)["request_sha256"], hashlib.sha256(frozen.encode()).hexdigest())
        self.assertEqual(self.meta(result)["write_state"], "SUBMITTED")
        gateway, transport, _ = self.gateway([])
        with self.assertRaises(ValueError):
            await self.invoke(gateway, 'retain', self.retain_args(operation=None))
        self.assertEqual(transport.calls, [])

    async def test_uncertain_retain_second_call_only_queries_original_operation(self):
        for status in ("pending", "processing", "completed", "failed", "cancelled"):
            with self.subTest(status=status):
                gateway, transport, _ = self.gateway([
                    {"error": adapter.TransportFailure("TIMEOUT", "upstream_tool_roundtrip", True)},
                    {"result": adapter.result_body({"state": "RESPONSE", "body": {
                        "operation_id": OPERATION, "status": status}})},
                ])
                result = await self.invoke(gateway, "retain", self.retain_args())
                self.assertEqual([(c["protocol"], c["tool"]) for c in transport.calls],
                                 [("mcp", "retain"), ("api", "get_operation")])
                self.assertEqual(transport.calls[1]["arguments"], {"bank_id": BANK, "operation_id": OPERATION})
                self.assertEqual(self.meta(result)["operation_status"], status)
                self.assertEqual(self.meta(result)["write_state"], "RECONCILED")
                self.assertTrue(self.meta(result)["attempts"][1]["reconcile_only"])

    async def test_uppercase_uuid_ack_and_reconciliation_compare_values(self):
        original = self.retain_args(operation=OPERATION.upper())
        gateway, transport, _ = self.gateway([
            {'result': adapter.result_body({'status': 'accepted', 'operation_id': OPERATION})}])
        result = await self.invoke(gateway, 'retain', original)
        self.assertEqual(self.meta(result)['write_state'], 'SUBMITTED')
        self.assertEqual(len(transport.calls), 1)
        gateway, transport, _ = self.gateway([
            {'error': adapter.TransportFailure('TIMEOUT', 'upstream_tool_roundtrip', True)},
            {'result': adapter.result_body({'operation_id': OPERATION, 'status': 'completed'})}])
        result = await self.invoke(gateway, 'retain', original)
        self.assertEqual(self.meta(result)['write_state'], 'RECONCILED')
        self.assertEqual([c['tool'] for c in transport.calls], ['retain', 'get_operation'])

    async def test_api_fallback_preserves_explicit_null_retain_fields(self):
        original = self.retain_args()
        original.update(context=None, tags=None, timestamp=None, strategy=None)
        request = adapter.api_request('retain', original, 70)
        routing = {k: request[k] for k in ('bank_id', 'operation_id', 'document_id')}
        self.assertEqual({**request['payload'], **routing}, original)
        self.assertIsNone(request['payload']['context'])
        self.assertIsNone(request['payload']['tags'])
        self.assertEqual(request['timeout_seconds'], 70)

    async def test_unknown_reconciliation_does_not_blindly_retain_again(self):
        responses = (
            {"result": adapter.result_body({"operation_id": OPERATION, "status": "not_found"})},
            {"result": adapter.result_body({"operation_id": "foreign-operation", "status": "completed"})},
            {"error": adapter.TransportFailure("NETWORK", "api_relay_roundtrip", True)},
        )
        for second in responses:
            with self.subTest(second=second):
                gateway, transport, _ = self.gateway([
                    {"error": adapter.TransportFailure("TIMEOUT", "upstream_tool_roundtrip", True)}, second])
                result = await self.invoke(gateway, "retain", self.retain_args())
                self.assertTrue(result["isError"])
                self.assertEqual(adapter.native_body(result)["state"], "UNKNOWN")
                self.assertEqual(self.meta(result)["operation_id"], OPERATION)
                self.assertEqual([c["tool"] for c in transport.calls], ["retain", "get_operation"])

    async def test_unknown_native_receipt_and_malformed_ack_use_only_remaining_reconciliation(self):
        responses = (
            adapter.result_body({"state": "UNKNOWN", "request_started": True,
                                 "error": {"code": "REQUEST_FAILED"}}, True),
            adapter.result_body({"status": "accepted", "operation_id": "foreign-operation"}),
            {"content": [{"type": "text", "text": "not a valid JSON acknowledgement"}], "isError": False},
        )
        for response in responses:
            with self.subTest(response=response):
                gateway, transport, _ = self.gateway([
                    {"result": response},
                    {"result": adapter.result_body({"operation_id": OPERATION, "status": "not_found"})},
                ])
                result = await self.invoke(gateway, "retain", self.retain_args())
                self.assertTrue(result["isError"])
                self.assertEqual(adapter.native_body(result)["state"], "UNKNOWN")
                self.assertEqual([c["tool"] for c in transport.calls], ["retain", "get_operation"])

    async def test_shared_deadline_includes_attempts_and_sleep_and_never_resets_on_api_switch(self):
        gateway, transport, clock = self.gateway([
            {"elapsed": "timeout", "error": adapter.TransportFailure("PROTOCOL", "mcp_initialize")},
            {"elapsed": "timeout", "result": adapter.result_body({"matches": []})},
        ])
        result = await self.invoke(gateway)
        self.assertEqual([c["protocol"] for c in transport.calls], ["mcp", "api"])
        first, second = transport.calls
        self.assertEqual(first["timeout"], 90)
        self.assertEqual(clock.sleeps, [3])
        self.assertLess(second["timeout"], 90)
        self.assertLessEqual(second["started"] + second["timeout"], 180)
        self.assertLessEqual(self.meta(result)["elapsed_ms"], 180000)
        gateway, transport, _ = self.gateway([
            {"elapsed": 3, "error": adapter.TransportFailure("NETWORK", "ssh_connect_exec")},
            {"result": adapter.result_body({"should_not": "run"})},
        ])
        result = await self.invoke(gateway, timeout=3)
        self.assertEqual(len(transport.calls), 1)
        self.assertTrue(result["isError"])

    async def test_invalid_timeout_or_retain_identity_fails_before_transport(self):
        for timeout in (0, -1, 181, True, "90"):
            with self.subTest(timeout=timeout):
                gateway, transport, _ = self.gateway([])
                with self.assertRaises(ValueError):
                    await self.invoke(gateway, timeout=timeout)
                self.assertEqual(transport.calls, [])
        for changes in ({"document_id": ""}, {"operation_id": "not-a-uuid"}):
            gateway, transport, _ = self.gateway([])
            with self.assertRaises(ValueError):
                await self.invoke(gateway, "retain", {**self.retain_args(), **changes})
            self.assertEqual(transport.calls, [])

    async def test_list_banks_filters_unauthorized_banks_and_recomputes_count(self):
        raw = {"banks": [{"bank_id": BANK, "name": "authorized"}, {"bank_id": "other-project"},
                         {"id": BANK, "name": "legacy authorized identity"}, {"bank_id": "default"}], "total": 987}
        for response in (adapter.result_body(raw), adapter.result_body({"state": "RESPONSE", "body": raw})):
            gateway, transport, _ = self.gateway([{"result": response}])
            result = await self.invoke(gateway, "list_banks", {})
            body = adapter.native_body(result)
            self.assertEqual(body["banks"], [raw["banks"][0], raw["banks"][2]])
            self.assertEqual(body["total"], 2)
            self.assertEqual(len(transport.calls), 1)
            self.assertNotIn("other-project", json.dumps(result))

    async def test_all_project_bank_discovery_matches_call_authorization(self):
        valid = [{'bank_id': BANK}, {'bank_id': 'future-project'}, {'id': 'legacy-project'}]
        raw = {'banks': valid + [{'bank_id': bank} for bank in
                                ('default', 'DEFAULT', '', ' ', 'project ', None, 17)]
                        + [{}, 'invalid record'], 'total': 987}
        for response in (adapter.result_body(raw), adapter.result_body({'state': 'RESPONSE', 'body': raw})):
            gateway, _, _ = self.gateway([{'result': response}])
            result = await self.invoke(gateway, 'list_banks', {}, all_project_banks=True)
            body = adapter.native_body(result)
            self.assertEqual(body['banks'], valid)
            self.assertEqual(body['total'], len(valid))


if __name__ == "__main__":
    unittest.main()
