from datetime import timedelta
from typing import List


def split_string(string: str) -> List[str]:
    """
    Split a string into a list of strings of length < 4096.
    :param string: the string to split
    :return: a list of strings
    """
    if len(string) < 4096:
        return [string]
    words = string.split()
    result = []
    current_string = ""
    for word in words:
        if len(current_string) + len(word) > 4095:
            result.append(current_string)
            current_string = word
        else:
            current_string += f" {word}"
    result.append(current_string)
    return result


def format_timedelta(td: timedelta) -> str:
    """
    Format a timedelta object into a string
    """
    days = td.days
    hours, remainder = divmod(td.seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    result = []
    if days > 0:
        result.append(f"{days} days")
    if hours > 0:
        result.append(f"{hours} hours")
    if minutes > 0:
        result.append(f"{minutes} minutes")
    if seconds > 0:
        result.append(f"{seconds} seconds")
    return " e ".join(result)
