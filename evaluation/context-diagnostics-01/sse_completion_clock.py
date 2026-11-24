"""Record the dispatched SSE terminal event separately from EOF/audit cleanup.

Transport bytes remain opaque. This does not validate a reply, settle a bill,
stop collection, or authorize a further request. Existing protocol/financial
validation must still succeed before the reply may be used.
"""
import time


def read_with_completion_clock(response,clock=time.monotonic):
    chunks=[];done_at=None;data_count=0;done_data=False;error_event=False
    while True:
        line=response.readline()
        if not line:break
        chunks.append(line)
        if line in (b'\n',b'\r\n'):
            if data_count==1 and done_data and not error_event:
                done_at=clock()
                # Continue to EOF for durable collection and trailing-error
                # validation. The clock alone never makes this reply usable.
                chunks.append(response.read())
                break
            data_count=0;done_data=False;error_event=False
        elif line.startswith(b'data:'):
            data_count+=1;done_data=line[5:].strip()==b'[DONE]'
        elif line.startswith(b'event:'):
            error_event=line[6:].strip()==b'error'
    return b''.join(chunks),done_at
