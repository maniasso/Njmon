#!/usr/bin/python3
# convert concatenated pretty to line separated

import sys
import json

text = ""

for line in sys.stdin:
    #if line[0:3] == "  {":
    #	 continue
    #if line[0:3] == "  }":
    #    continue
    #if line[0:4] == "  },":
    #    line="}"
    #
    #if line[0:3] == "  {":
    #    saving=1

    text=text+line

    if line[0:1] == "}":
         print(json.dumps(json.loads(text)))
         text=""

