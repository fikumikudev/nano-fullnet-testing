from decorator import decorator


def env_data_to_list(env: dict) -> list:
    return [f"{key}={value}" for (key, value) in env.items()]


@decorator
def title_bar(func, name=None, *args, **kw):
    print(f"================ {name} ================")
    result = func(*args, **kw)
    print(f"================ DONE")
    return result
