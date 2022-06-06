def load_env_data_as_dict(path: str) -> dict:
    with open(path, "r") as f:
        return dict(
            tuple(line.replace("\n", "").split("="))
            for line in f.readlines()
            if line.strip() and not line.startswith("#")
        )
        # return dict(
        #     print(line.replace("\n", "").split("="))
        #     for line in f.readlines()
        #     if line and not line.startswith("#")
        # )


def env_data_to_list(env: dict) -> list:
    return [f"{key}={value}" for (key, value) in env.items()]
