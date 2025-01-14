import code
import sys
import traceback
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from typing import Any, Callable, Dict, List, Optional, Tuple

# Import bridge functions
from _bridge_functions import __call_host_function, __wait_for_host


class REPL(code.InteractiveInterpreter):
    def __init__(
        self, variables: Dict[Any, Any] = None, funcs: List[Callable] = None
    ):
        variables = variables or {}
        funcs = funcs or []

        super().__init__(locals=variables)
        self.globals = variables
        for func in funcs:
            self.globals[func.__name__] = func

        self.__stdout = StringIO()
        self.__stderr = StringIO()

    def runcode(
        self, code_str: str
    ) -> Tuple[Any, Optional[Exception], str, str]:
        """
        Run the given code, storing locals and globals over time.

        Args:
            code_str: The code to execute

        Returns:
            Tuple containing:
            - The result of the execution (if any)
            - The exception that was raised (if any)
            - stdout from the execution
            - stderr from the execution
        """
        result = None
        exception = None
        self.__stdout = StringIO()
        self.__stderr = StringIO()

        try:
            with redirect_stdout(self.__stdout), redirect_stderr(self.__stderr):
                code_obj = compile(code_str, "<repl>", "single")
                result = eval(code_obj, self.globals, self.locals)

        except Exception as e:
            exception = e
            self.__stderr.write(
                "".join(traceback.format_exception(type(e), e, e.__traceback__))
            )

        return (
            result,
            exception,
            self.__stdout.getvalue(),
            self.__stderr.getvalue(),
        )


def __repl_main():
    """Main REPL loop that handles incoming code execution requests."""
    # Initialize REPL with available tools
    repl = REPL(funcs=[{tool_names}])

    # Wait for initial connection
    __wait_for_host()

    while True:
        try:
            # Wait for code execution request from host
            response = __call_host_function("_wait_for_execution")

            if not response or not isinstance(response, dict):
                continue

            if "code" not in response:
                continue

            # Execute the code
            result, exception, stdout, stderr = repl.runcode(response["code"])

            # Send results back to host
            __call_host_function(
                "_execution_result",
                result=result,
                exception=exception,
                stdout=stdout,
                stderr=stderr,
            )

        except Exception as e:
            # If something goes wrong with the communication,
            # try to send the error back
            try:
                __call_host_function(
                    "_execution_result",
                    result=None,
                    exception=str(e),
                    stdout="",
                    stderr=f"REPL Error: {str(e)}\n",
                )
            except Exception as e:
                # If we can't even send the error, just print it
                print(f"Fatal REPL error: {e}", file=sys.stderr)
            finally:
                continue


if __name__ == "__main__":
    __repl_main()
