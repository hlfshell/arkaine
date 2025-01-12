import socket
from {client_import} import *

import code
import sys
import os

from contextlib import redirect_stdout, redirect_stderr
from typing import Any, Callable, Dict, List, Tuple
from io import StringIO

class REPL(code.InteractiveInterpreter):
    def __init__(self, variables: Dict[Any, Any] = {}, funcs: List[Callable] = []):
        self.locals = {}
        self.globals = variables
        for func in funcs:
            self.globals[func.__name__] = func
        self.__stdout = StringIO()
        self.__stderr = StringIO()
    
    def runcode(self, code: str) -> Tuple[str, str]:
        """
        Run the given code, storing locals and globals
        over time. Return the stdout and stderr respectively
        of the execution.
        """
        with redirect_stdout(self.__stdout), redirect_stderr(self.__stderr):
            super().runcode(code, self.locals, self.globals)
        return self.__stdout.getvalue(), self.__stderr.getvalue()
    

def __repl_main():
    repl = REPL(
        funcs=[
            {tool_names}
        ]
    )

    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    sock.connect("/{code_directory}/{socket_file}")
    while True:
        data = __wait_for_data(sock)
        
        if data["function"] == "repl":
            stdout, stderr = repl.runcode(data["code"])
            __send_result(stdout, stderr)


if __name__ == "__main__":
    __repl_main()