"""Base classes for tools
"""
from typing_extensions import Union
import asyncio


def asyncio_db_loop(method):
    """Decorator for checking that an event loop is present for handling asynchronous callse

    :param method: Function which has asynchronous process
    :type method: None
    """
    def wrapper(self, *args, **kwargs):
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError as e:
            if str(e).startswith('There is no current event loop in thread'):
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
            else:
                raise

        result = method(self, *args, **kwargs)
        return result

    return wrapper





