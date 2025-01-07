from multiprocessing import Pool

from {client_import} import __send_exception, __send_result


def run_script():
    try:
        script = __import__("{target_file}".removesuffix(".py"))
        result = script.{main_function}()
        __send_result(result)
        return result
    except Exception as e:
        __send_exception(e)
        return None

def execute_code():
    with Pool(processes=1) as pool:
        return pool.apply(
            run_script,
        )

if __name__ == "__main__":
    execute_code()
