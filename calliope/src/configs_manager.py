import re
from pathlib import Path
from typing import Any, Dict, Union

import yaml
from loguru import logger

# from calliope.src.utils.logger_setter import logger_setter

# TODO: find a better solution for this
# logger_setter()


class ConfigsNotFoundError(Exception):
    """
    Custom exception raised when configuration files are not found.

    Args:
        num_files (Union[int, None]): Number of configuration files found. Defaults to None.
    """

    def __init__(self, num_files: Union[int, None] = None):
        """
        Initialize the exception.

        Args:
            num_files (Union[int, None]): Number of configuration files found. Defaults to None.
        """
        self.num_files = num_files
        if self.num_files:
            self.message = f"There is {self.num_files} yaml files in the conf directory, specify wich one you want to use"
        else:
            self.message = "Configuration file not found"

        super().__init__(self.message)


# TODO: use lrucache for configs loading
class ConfigsLoader(dict):
    """A class for loading and processing configuration data from a YAML file."""

    def __init__(self, path: Union[str, None] = None) -> None:
        """
        Initialize the ConfigsLoader.

        Args:
            path (Union[str, None], optional): The path to the YAML file. If not provided, it searches for YAML files in the "conf" folder.
        """
        super().__init__()
        self.load(path=path)

    def load(self, path: str) -> None:

        with open(path, "r") as f:
            data = yaml.safe_load(f)
            self.update(data)


settings = ConfigsLoader("calliope/src/config/configs.yaml")
