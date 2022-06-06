def env_data_to_list(env: dict) -> list:
    return [f"{key}={value}" for (key, value) in env.items()]
