import ast
import re
import sys
import time
import uuid

from ipykernel.kernelbase import Kernel
from .ubit import connect, disconnect

__version__ = '0.4'

class MicrobitKernel(Kernel):
    implementation = 'ubit_kernel'
    implementation_version = __version__

    language_info = {'name': 'python',
                     'version': '3',
                     'mimetype': 'text/x-python',
                     'file_extension': '.py',
                     'codemirror_mode': {'name': 'python',
                                         'version': 3},
                     'pygments_lexer': 'python3',
                    }

    help_links = [
        {'text': 'micro:bit MicroPython',
         'url': 'http://microbit-micropython.readthedocs.org/en/latest/index.html'
        },
    ]

    banner = "Welcome to MicroPython on the BBC micro:bit"
    INIT_CODE = '''try:
    g['UUID'] = {}
except NameError:
    g = {'UUID': {}}
try:
    l['UUID'] = {}
except NameError:
    l = {'UUID': {}}
'''

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.uuid = uuid.uuid4().hex
        self.serial = connect()

        out, err = self.run_code(self.INIT_CODE.replace('UUID', self.uuid))
        self.send_response(self.iopub_socket, 'stream', {
            'name': 'stdout',
            'text': 'Kernel connected to microbit, uuid: %s' % self.uuid,
        })

    def run_code(self, code):
        '''Run a string of code, return strings for stdout and stderr'''
        try:
            self.serial.write(b'\x03' + code.encode('utf-8') + b'\x04')
            result = bytearray()
            while not result.endswith(b'\x04>'):
                time.sleep(0.1)
                result.extend(self.serial.read_all())

            return self._parse_result(result)

        except KeyboardInterrupt:
            self.serial.write(b'\x03')
            time.sleep(0.1)
            self.serial.reset_output_buffer()
            self.serial.reset_input_buffer()
            return self._parse_result(result)

    def _parse_result(self, result):
        if result.startswith(b'OK'):
            results = result[2:-2].split(b'\x04', 1)
            if len(results) == 2:
                out, err = results
            else:
                out, err = result, b''
            return out.decode('utf-8', 'replace'), err.decode('utf-8', 'replace')
        else:
            return '', 'something is not ok'

    def do_execute(self, code, silent, store_history=True,
                   user_expressions=None, allow_stdin=False):
        real_code = 'exec({code!r}, g[{uuid!r}], l[{uuid!r}])'
        formatted_code = real_code.format(code=code, uuid=self.uuid)
        print(formatted_code)
        out, err = self.run_code(formatted_code)
        if out:
            self.send_response(self.iopub_socket, 'stream', {
                'name': 'stdout',
                'text': out
            })
        if err:
            self.send_response(self.iopub_socket, 'stream', {
                'name': 'stderr',
                'text': err
            })

        return {'status': 'ok', 'execution_count': self.execution_count,
                'payload': [], 'user_expressions': {}}

    def _eval(self, expr):
        out, err = self.run_code('print({})'.format(expr))
        return ast.literal_eval(out)

    def do_complete(self, code, cursor_pos):
        #print('completing on', repr(code), file=sys.__stderr__)
        code = code[:cursor_pos]
        m = re.search(r'(\w+\.)*(\w+)?$', code)
        if m:
            prefix = m.group()
            #print('prefix', repr(prefix), file=sys.__stderr__)
            if '.' in prefix:
                obj, prefix = prefix.rsplit('.')
                names = self._eval('dir({})'.format(obj))
            else:
                names = self._eval('dir()')
            #print('names', names, file=sys.__stderr__)
            matches = [n for n in names if n.startswith(prefix)]
            return {'matches': matches,
                    'cursor_start': cursor_pos - len(prefix), 'cursor_end': cursor_pos,
                    'metadata': {}, 'status': 'ok'}
        else:
            return {'matches': [],
                    'cursor_start': cursor_pos, 'cursor_end': cursor_pos,
                    'metadata': {}, 'status': 'ok'}

    def do_shutdown(self, restart):
        code = 'del g[{uuid!r}]; del l[{uuid!r}]'
        out, err = self.run_code(code.format(uuid=self.uuid))
        disconnect()
        return {
            'restart': restart,
        }
