#!/usr/bin/python3
# Convert one JOSN per line to pretty output
import sys
import json

count = 0
cached = 0
entry = []

for line in sys.stdin:
    count = count + 1
    #j=json.loads(line)
    #print(json.dumps(j, indent=4, sort_keys=True))
    print(json.dumps(json.loads(line), indent=4, sort_keys=True))

# print("processed %s"%(count))
