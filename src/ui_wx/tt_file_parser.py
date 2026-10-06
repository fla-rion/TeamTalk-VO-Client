# Re-export from canonical location (src/ui/tt_file_parser.py) – früher eine
# identische Kopie, die bei Änderungen leicht auseinanderlief.
from ui.tt_file_parser import *  # noqa: F401, F403
from ui.tt_file_parser import (  # noqa: F401
    CHANNEL_TYPE_MASK,
    build_teamtalk_url,
    build_teamtalk_xml,
    parse_teamtalk_file,
    parse_teamtalk_url,
    parse_teamtalk_xml_text,
)
