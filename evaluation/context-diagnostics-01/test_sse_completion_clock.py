import io
import unittest
from sse_completion_clock import read_with_completion_clock


class DelayedEOF:
    def __init__(self,data,tail=b''):
        self.input=io.BytesIO(data);self.tail=tail;self.now=0.;self.drained=False
    def readline(self):self.now+=.01;return self.input.readline()
    def read(self):
        self.now+=10;self.drained=True
        return self.input.read()+self.tail


class CompletionClockTests(unittest.TestCase):
    def test_complete_reply_time_precedes_slow_cleanup_but_collection_still_drains(self):
        raw=b'data: {"public_test":"only"}\n\ndata: [DONE]\n\n'
        response=DelayedEOF(raw,b': trailing keepalive\n\n')
        data,done=read_with_completion_clock(response,lambda:response.now)
        self.assertEqual(data,raw+b': trailing keepalive\n\n');self.assertTrue(response.drained)
        self.assertAlmostEqual(done,.04);self.assertGreater(response.now-done,9)

    def test_text_containing_done_is_not_a_terminal_event(self):
        response=DelayedEOF(b'data: {"public_text":"[DONE]"}\n\n')
        _,done=read_with_completion_clock(response,lambda:response.now);self.assertIsNone(done)

    def test_undispatched_or_multiline_or_error_event_is_not_a_complete_marker(self):
        for data in [b'data: [DONE]\n',b'data: other\ndata: [DONE]\n\n',b'event: error\ndata: [DONE]\n\n']:
            with self.subTest(data=data):
                response=DelayedEOF(data);raw,done=read_with_completion_clock(response,lambda:response.now)
                self.assertEqual(raw,data);self.assertIsNone(done)

    def test_trailing_error_bytes_are_preserved_for_existing_validator(self):
        response=DelayedEOF(b'data: [DONE]\r\n\r\n',b'event: error\ndata: {"error":"late"}\n\n')
        raw,done=read_with_completion_clock(response,lambda:response.now)
        self.assertIsNotNone(done);self.assertIn(b'event: error',raw)


if __name__=='__main__':unittest.main()
