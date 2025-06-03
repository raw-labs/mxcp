from typing import Any, Optional
from dataclasses import dataclass
from lsprotocol import types
from bisect import bisect_right
from lsprotocol import types
from pygls.workspace import TextDocument


@dataclass
class Parameter:
    name: str
    type: str
    description: Optional[str] = None
    default: Optional[Any] = None


class SQLValidation:

    def __init__(self, validation_result: Any, code: str):
        self.error = validation_result["error"]
        if self.error:
            self.error_type = validation_result["error_type"]
            self.error_message = validation_result["error_message"]
            self.error_subtype = validation_result["error_subtype"]
            self.position = int(validation_result["position"])
            self.error_position = self.__offset_to_position(code, self.position)

    def __offset_to_position(self, code: str, offset: int) -> types.Position:
        """
        Convert a 0-based character offset into an LSP Position.

        Parameters
        ----------
        code : str
            The code string to analyze.
        offset : int
            Absolute offset (0 == first byte / code-unit of the code).

        Returns
        -------
        types.Position
            LSP position (line, character), both 0-based.
        """
        if offset < 0 or offset > len(code):
            raise ValueError("offset is outside the code")

        # Split code into lines
        lines = code.split('\n')
        
        # Calculate line starts
        line_starts = [0]
        for line in lines[:-1]:
            # +1 for the newline character
            line_starts.append(line_starts[-1] + len(line) + 1)

        # Fast O(log n) lookup
        line = bisect_right(line_starts, offset) - 1
        character = offset - line_starts[line]
        return types.Position(line=line, character=character)

    def is_error(self) -> bool:
        return self.error 