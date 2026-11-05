"""Bounded SSH/stdin MCP transport. No payload store, queue or implicit retry."""
import asyncio
import base64
from copy import deepcopy
import hashlib
import json
import logging
import random
import time
from uuid import UUID, uuid4

MAX_MESSAGE = 16 * 1024 * 1024
API_TOOLS = frozenset({'recall', 'reflect', 'retain', 'get_operation',
                       'get_document', 'list_operations', 'list_banks'})
LOG = logging.getLogger('hindsight.gateway')


def same_operation(left, right):
    if not isinstance(left, str) or not isinstance(right, str):
        return False
    try:
        return UUID(left) == UUID(right)
    except ValueError:
        return False


def api_request(tool, arguments, timeout):
    request = {'action': tool, 'timeout_seconds': min(90.0, timeout)}
    for field in ('bank_id', 'operation_id', 'document_id', 'query'):
        if field in arguments:
            request[field] = arguments[field]
    # Explicit nulls are part of the frozen source payload, including retain.
    request['payload'] = {k: v for k, v in arguments.items() if k not in request}
    return request


class TransportFailure(Exception):
    def __init__(self, kind, phase, sent=False):
        self.kind, self.phase, self.sent = kind, phase, sent
        super().__init__(kind)


def native_body(result):
    """Unwrap native FastMCP string results without inventing completion."""
    value = result.get('structuredContent')
    if isinstance(value, dict):
        if set(value) == {'result'} and isinstance(value['result'], str):
            try:
                return json.loads(value['result'])
            except ValueError:
                return None
        return value
    for block in result.get('content', []):
        if block.get('type') == 'text':
            try:
                return json.loads(block['text'])
            except (ValueError, KeyError):
                continue
    return None


def result_body(body, error=False):
    return {'content': [{'type': 'text', 'text': json.dumps(body, ensure_ascii=False)}],
            'structuredContent': body, 'isError': error}


class SSHTransport:
    def __init__(self, config):
        self.config = config

    def command(self, protocol):
        path = self.config['mcp_script' if protocol == 'mcp' else 'api_script']
        python = self.config['python']
        # Configuration is trusted installation input, never a tool argument.
        if any("'" in v or '\n' in v or '\r' in v for v in (path, python)):
            raise ValueError('Unsupported configured Windows path')
        script = ("$env:PYTHONUTF8='1';$env:PYTHONIOENCODING='utf-8';"
                  "[Console]::Error.WriteLine('HINDSIGHT_REMOTE_READY');"
                  f"& '{python}' '{path}'")
        encoded = base64.b64encode(script.encode('utf-16le')).decode('ascii')
        return ['ssh', '-F', self.config['ssh_config'], '-T',
                '-o', 'BatchMode=yes', '-o', 'StrictHostKeyChecking=yes',
                '-o', 'ControlMaster=no', '-o', 'ControlPath=none',
                self.config['ssh_host'],
                'powershell.exe -NoLogo -NoProfile -NonInteractive -EncodedCommand ' + encoded]

    async def call(self, protocol, tool, arguments, timeout, trace):
        started = time.monotonic()
        process = None
        stderr_task = None
        phase, sent, auth_failed = 'ssh_connect_exec', False, False
        remote_started = False
        remote_ready = asyncio.Event()
        timings = trace['phases_ms']

        async def stderr():
            nonlocal auth_failed, remote_started
            while line := await process.stderr.readline():
                # Never log raw stderr: libraries may include private payloads.
                if b'HINDSIGHT_REMOTE_READY' in line:
                    remote_started = True
                    remote_ready.set()
                    timings['ssh_connect_exec'] = round((time.monotonic()-started)*1000, 2)
                if any(s in line.lower() for s in (b'permission denied', b'host key verification failed')):
                    auth_failed = True
            remote_ready.set()

        async def send(value):
            data = (json.dumps(value, ensure_ascii=False, allow_nan=False)+'\n').encode('utf-8')
            if len(data) > MAX_MESSAGE:
                raise ValueError('Request exceeds 16 MiB transport limit')
            process.stdin.write(data)
            await process.stdin.drain()

        async def reply(identifier):
            while True:
                line = await process.stdout.readline()
                if not line:
                    await process.wait()
                    # stderr reader must finish before permission classification.
                    await stderr_task
                    kind = 'AUTHENTICATION_FAILED' if auth_failed else (
                        'NETWORK' if process.returncode == 255 else 'SESSION')
                    raise TransportFailure(kind, phase, sent)
                try:
                    data = json.loads(line)
                except ValueError:
                    raise TransportFailure('PROTOCOL', phase, sent) from None
                if not isinstance(data, dict):
                    raise TransportFailure('PROTOCOL', phase, sent)
                if data.get('id') == identifier:
                    if 'error' in data:
                        # Native tool/RPC errors are not evidence of a broken session.
                        if phase == 'mcp_initialize':
                            raise TransportFailure('PROTOCOL', phase, sent)
                        return result_body({'state': 'RESPONSE', 'rpc_error': data['error']}, True)
                    if not isinstance(data.get('result'), dict):
                        raise TransportFailure('PROTOCOL', phase, sent)
                    return data['result']
                if 'id' in data and 'method' in data:
                    await send({'jsonrpc': '2.0', 'id': data['id'],
                                'error': {'code': -32601, 'message': 'Client request unsupported'}})

        try:
            # Reserve bounded local cleanup inside the attempt budget.
            work_deadline = started+max(.001, timeout-.5)
            async with asyncio.timeout_at(work_deadline):
                process = await asyncio.create_subprocess_exec(
                    *self.command(protocol), stdin=asyncio.subprocess.PIPE,
                    stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
                    limit=MAX_MESSAGE)
                stderr_task = asyncio.create_task(stderr())
                if protocol == 'mcp':
                    phase = 'mcp_initialize'
                    await send({'jsonrpc': '2.0', 'id': 1, 'method': 'initialize', 'params': {
                        'protocolVersion': '2025-03-26', 'capabilities': {},
                        'clientInfo': {'name': 'hindsight-vps', 'version': '1.0.0'}}})
                    init = await reply(1)
                    if init.get('protocolVersion') != '2025-03-26':
                        raise TransportFailure('PROTOCOL', phase)
                    timings['mcp_initialize_including_ssh'] = round((time.monotonic()-started)*1000, 2)
                    await send({'jsonrpc': '2.0', 'method': 'notifications/initialized'})
                    phase = 'upstream_tool_roundtrip'
                    call_start = time.monotonic()
                    # sent=True is conservative: a partial pipe write is uncertain too.
                    sent = True
                    await send({'jsonrpc': '2.0', 'id': 2, 'method': 'tools/call',
                                'params': {'name': tool, 'arguments': arguments}})
                    answer = await reply(2)
                    timings[phase] = round((time.monotonic()-call_start)*1000, 2)
                    return answer
                phase = 'api_relay_roundtrip'
                await remote_ready.wait()
                if not remote_started:
                    await process.wait()
                    raise TransportFailure('AUTHENTICATION_FAILED' if auth_failed else 'NETWORK', 'ssh_connect_exec')
                request = api_request(tool, arguments, max(.001, work_deadline-time.monotonic()))
                sent = True
                await send(request)
                process.stdin.close()
                line = await process.stdout.readline()
                if not line:
                    await process.wait()
                    await stderr_task
                    raise TransportFailure('AUTHENTICATION_FAILED' if auth_failed else
                                           ('NETWORK' if process.returncode == 255 else 'SESSION'), phase, sent)
                try:
                    receipt = json.loads(line)
                except ValueError:
                    raise TransportFailure('PROTOCOL', phase, sent) from None
                if not isinstance(receipt, dict) or receipt.get('action') != tool:
                    raise TransportFailure('PROTOCOL', phase, sent)
                for key in ('bank_id', 'operation_id', 'document_id'):
                    matches = (same_operation(receipt.get(key), arguments.get(key)) if key == 'operation_id'
                               else receipt.get(key) == arguments.get(key))
                    if key in arguments and not matches:
                        raise TransportFailure('PROTOCOL', phase, sent)
                timings[phase] = round((time.monotonic()-started)*1000, 2)
                trace['relay_state'] = receipt.get('state')
                return result_body(receipt, receipt.get('state') in {'UNKNOWN', 'NOT_SUBMITTED'}
                                   or receipt.get('http_status', 200) >= 400)
        except TimeoutError:
            raise TransportFailure('TIMEOUT', phase, sent) from None
        except (OSError, BrokenPipeError, ConnectionError):
            raise TransportFailure('NETWORK', phase, sent) from None
        except ValueError:
            raise TransportFailure('PROTOCOL', phase, sent) from None
        finally:
            # Terminating our SSH process does not prove a Win operation stopped.
            if process is not None and process.returncode is None:
                try:
                    process.terminate()
                except ProcessLookupError:
                    pass
                try:
                    await asyncio.wait_for(process.wait(), .25)
                except TimeoutError:
                    try:
                        process.kill()
                    except ProcessLookupError:
                        pass
                    try:
                        await asyncio.wait_for(process.wait(), .25)
                    except TimeoutError:
                        trace['local_cleanup_timeout'] = True
            if stderr_task is not None:
                stderr_task.cancel()
                await asyncio.gather(stderr_task, return_exceptions=True)
            timings['attempt_elapsed'] = round((time.monotonic()-started)*1000, 2)


class Gateway:
    def __init__(self, transport, catalog, *, clock=time.monotonic,
                 sleep=asyncio.sleep, jitter=lambda: random.uniform(2, 5)):
        self.transport, self.clock, self.sleep, self.jitter = transport, clock, sleep, jitter
        self.catalog = {t['name']: t for t in catalog['tools']}
        self.schema_hash = hashlib.sha256(json.dumps(catalog, sort_keys=True).encode()).hexdigest()
        if len(self.catalog) != 39:
            raise ValueError('M1 catalog must contain exactly 39 reviewed tools')
        for name, tool in self.catalog.items():
            if name != 'list_banks' and ('bank_id' not in tool['inputSchema'].get('properties', {})
                                        or 'bank_id' not in tool['inputSchema'].get('required', [])):
                raise ValueError('Unscoped upstream tool')

    async def invoke(self, tool, arguments, *, allowed_banks, protocol='mcp', timeout=180):
        from jsonschema import Draft202012Validator, ValidationError
        started = self.clock()
        if isinstance(timeout, bool) or not isinstance(timeout, (int, float)) or not 0 < timeout <= 180:
            raise ValueError('timeout_seconds must be in (0, 180]')
        if protocol not in {'mcp', 'api'} or (protocol == 'api' and tool not in API_TOOLS):
            raise ValueError('Unsupported protocol/tool combination')
        if tool not in self.catalog or not isinstance(arguments, dict):
            raise ValueError('Unknown tool or invalid arguments')
        args = deepcopy(arguments)
        try:
            Draft202012Validator(self.catalog[tool]['inputSchema']).validate(args)
        except ValidationError:
            raise ValueError('Arguments do not match the reviewed tool schema') from None
        bank = args.get('bank_id')
        if tool != 'list_banks' and (bank not in allowed_banks or bank != bank.strip()
                                    or not bank or bank.casefold() == 'default'):
            raise PermissionError('Project bank is not authorized for this principal')
        if tool == 'retain':
            # Caller must possess the UUID even if the public HTTP ACK is lost.
            if not isinstance(args.get('document_id'), str) or not args['document_id'].strip():
                raise ValueError('VPS retain requires a stable document_id')
            if not isinstance(args.get('operation_id'), str):
                raise ValueError('VPS retain requires a caller-allocated operation_id')
            UUID(args['operation_id'])
        request_id = str(uuid4())
        frozen = json.dumps(args, sort_keys=True, ensure_ascii=False, allow_nan=False)
        readonly = self.catalog[tool].get('annotations', {}).get('readOnlyHint') is True
        meta = {'request_id': request_id, 'attempts': [], 'request_sha256': hashlib.sha256(frozen.encode()).hexdigest(),
                'retry_owner': 'vps', 'max_attempts': 2, 'deadline_seconds': timeout,
                'upstream_api_processing_ms': None}
        if tool == 'retain':
            meta.update(operation_id=args['operation_id'], document_id=args['document_id'])
        deadline = started + timeout
        current, call_tool, call_args = protocol, tool, args
        reconciling = False
        uncertain_write = False
        result = None
        for number in (1, 2):
            remaining = deadline - self.clock()
            if remaining <= .5:
                break
            trace = {'number': number, 'protocol': current, 'tool': call_tool, 'phases_ms': {},
                     'recreated_session': number > 1, 'reconcile_only': reconciling}
            meta['attempts'].append(trace)
            try:
                result = await self.transport.call(current, call_tool, deepcopy(call_args),
                                                   min(90.0, remaining-.25), trace)
                body = native_body(result)
                if reconciling:
                    # This second attempt only queries the original UUID; never resubmits.
                    meta['write_state'] = 'UNKNOWN'
                    op = body.get('body', body) if isinstance(body, dict) else None
                    if isinstance(op, dict) and same_operation(op.get('operation_id'), args['operation_id']):
                        state = op.get('status')
                        meta['operation_status'] = state
                        if state in {'pending', 'processing', 'completed', 'failed', 'cancelled'}:
                            meta['write_state'] = 'RECONCILED'
                    break
                if isinstance(body, dict) and body.get('state') in {'UNKNOWN', 'NOT_SUBMITTED'}:
                    if body.get('error', {}).get('code') in {'CONNECT_FAILED', 'REQUEST_FAILED'}:
                        raise TransportFailure('NETWORK', 'api_relay_roundtrip',
                                               body.get('request_started', False))
                if (isinstance(body, dict) and readonly and
                        body.get('http_status') in {408, 502, 503, 504}
                        and not body.get('retry_after')
                        and not body.get('response_headers', {}).get('Retry-After')):
                    raise TransportFailure('NETWORK', 'api_relay_roundtrip', True)
                if tool == 'retain' and not isinstance(body, dict):
                    raise TransportFailure('INVALID_ACK', 'upstream_tool_roundtrip', True)
                if tool == 'retain' and isinstance(body, dict):
                    ack = body.get('body', body)
                    valid = (body.get('status') == 'accepted' or body.get('state') == 'SUBMITTED')
                    if valid and isinstance(ack, dict) and same_operation(ack.get('operation_id'), args['operation_id']):
                        meta['write_state'] = 'SUBMITTED'
                        break
                    if body.get('state') not in {'UNKNOWN'} and result.get('isError'):
                        break
                    raise TransportFailure('INVALID_ACK', 'upstream_tool_roundtrip', True)
                # Native tool errors (including auth/validation) never trigger fallback.
                break
            except TransportFailure as exc:
                trace.update(failure=exc.kind, failed_phase=exc.phase, request_may_have_started=exc.sent)
                result = None
                if exc.kind == 'AUTHENTICATION_FAILED' or number == 2:
                    break
                if not readonly and exc.sent:
                    uncertain_write = True
                    if tool != 'retain':
                        break
                    reconciling = True
                    current, call_tool = 'api', 'get_operation'
                    call_args = {'bank_id': bank, 'operation_id': args['operation_id']}
                elif exc.kind in {'PROTOCOL', 'SESSION'} and tool in API_TOOLS:
                    current = 'api'
                elif exc.kind not in {'NETWORK', 'TIMEOUT'}:
                    break
                remaining = deadline - self.clock()
                delay = min(self.jitter(), max(0, remaining-.5))
                if delay <= 0:
                    break
                trace['backoff_seconds'] = delay
                await self.sleep(delay)
        if result is None or (reconciling and meta.get('write_state') != 'RECONCILED'):
            state = 'UNKNOWN' if uncertain_write or (not readonly and any(a.get('request_may_have_started') for a in meta['attempts'])) else 'UNAVAILABLE'
            result = result_body({'state': state, 'operation_id': args.get('operation_id'),
                                  'document_id': args.get('document_id'),
                                  'message': 'Keep original IDs/hash and pending summary on the original task; no background replay.'}, True)
            if state == 'UNKNOWN':
                meta['write_state'] = state
        if tool == 'list_banks' and not result.get('isError'):
            body = native_body(result)
            if isinstance(body, dict) and 'body' in body:
                body = body['body']
            if not isinstance(body, dict) or not isinstance(body.get('banks'), list):
                result = result_body({'state': 'UNKNOWN', 'message': 'Invalid bank discovery response'}, True)
            else:
                banks = [b for b in body['banks'] if b.get('bank_id', b.get('id')) in allowed_banks]
                result = result_body({**body, 'banks': banks, 'total': len(banks)})
        meta['elapsed_ms'] = round((self.clock()-started)*1000, 2)
        result.setdefault('_meta', {})['hindsight_gateway'] = meta
        LOG.info(json.dumps({'request_id': request_id, 'tool': tool, 'protocol': protocol,
                             'is_error': result.get('isError', False), **meta}))
        return result
