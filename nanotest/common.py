from decorator import decorator


def env_data_to_list(env: dict) -> list:
    return [f"{key}={value}" for (key, value) in env.items()]


def strike(text):
    result = ""
    for c in text:
        result = result + c + "\u0336"
    return result


@decorator
def title_bar(func, name=None, no_header=False, no_footer=False, *args, **kw):
    if not no_header:
        print(f"================ {name} ================")

    result = func(*args, **kw)

    if not no_footer:
        print(f"================ {strike(name)}")

    return result
