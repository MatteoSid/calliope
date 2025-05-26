import os # Added os import
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

    def _substitute_env_vars(self, item: Any) -> Any:
        """
        Recursively substitutes environment variables in a loaded YAML structure.
        Placeholders like ${VAR_NAME} or ${VAR_NAME:-default_value} are replaced.
        """
        if isinstance(item, dict):
            return {k: self._substitute_env_vars(v) for k, v in item.items()}
        elif isinstance(item, list):
            return [self._substitute_env_vars(i) for i in item]
        elif isinstance(item, str):
            # Regex to find ${VAR_NAME} or ${VAR_NAME:-default}
            # Handles cases like ${VAR_NAME} and ${VAR_NAME:-default_value}
            pattern = re.compile(r"\$\{(?P<name>[A-Z_][A-Z0-9_]*)(?::-(?P<default>[^}]*))?\}")
            
            new_string = item
            # Need to process the string iteratively because re.sub doesn't handle overlapping matches
            # or allow for dynamic replacement logic based on whether the env var is found.
            
            # A string to build the result
            processed_parts = []
            last_end = 0 # End of the last processed match
            
            for match in pattern.finditer(new_string):
                var_name = match.group("name")
                default_val = match.group("default")

                env_value = os.getenv(var_name)
                
                value_to_substitute = None
                if env_value is not None:
                    value_to_substitute = env_value
                elif default_val is not None:
                    value_to_substitute = default_val
                else:
                    # If no env var and no default, replace the placeholder with an empty string.
                    # This means "http://localhost:${MY_PORT}" becomes "http://localhost:" if MY_PORT is not set.
                    # The factory function in summarization_llm.py will catch if essential values are then missing.
                    value_to_substitute = "" 

                # Add the part of the string before the current match
                processed_parts.append(new_string[last_end:match.start()])
                # Add the substituted value
                processed_parts.append(value_to_substitute)
                last_end = match.end()
            
            # Add any remaining part of the string after the last match
            processed_parts.append(new_string[last_end:])
            
            return "".join(processed_parts)
        return item

    def load(self, path: str) -> None:
        if not path:
            # This case should ideally be handled by the caller or have a default config path.
            # For now, raising an error if path is None or empty.
            raise ValueError("Configuration file path must be provided.")
            
        try:
            with open(path, "r") as f:
                data = yaml.safe_load(f)
        except FileNotFoundError:
            logger.error(f"Configuration file not found at path: {path}")
            raise ConfigsNotFoundError() # Or re-raise FileNotFoundError
        except yaml.YAMLError as e:
            logger.error(f"Error parsing YAML file at {path}: {e}")
            raise # Re-raise the YAML error

        # After loading, substitute environment variables
        if data: # Ensure data is not None (e.g. empty YAML file)
            processed_data = self._substitute_env_vars(data)
            self.update(processed_data)
        else:
            # If YAML is empty or only comments, data might be None.
            # self.update({}) ensures the dictionary is empty rather than erroring.
            self.update({})


settings = ConfigsLoader("calliope/src/config/configs.yaml")
