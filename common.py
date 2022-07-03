from decorator import decorator


def env_data_to_list(env: dict) -> list:
    return [f"{key}={value}" for (key, value) in env.items()]


def strike(text):
    result = ""
    for c in text:
        result = result + c + "\u0336"
    return result


@decorator
def title_bar(func, name=None, *args, **kw):
    print(f"================ {name} ================")
    result = func(*args, **kw)
    print(f"================ {strike(name)}")
    return result
