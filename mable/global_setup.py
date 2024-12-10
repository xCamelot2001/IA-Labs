from typing import Dict, Any

abc: Dict[str, Any] = {}


def done():
    global abc
    abc = {}
