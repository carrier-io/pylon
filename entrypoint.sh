#!/bin/bash

: "${PYLON_INIT:=dumb-init}"

if [ "$PYLON_INIT" = "pylon" ]; then
   exec python -m pylon.main
elif [ "$PYLON_INIT" = "dumb-init" ]; then
   exec dumb-init python -m pylon.main
else
  echo "Unknown init: $PYLON_INIT"
  exit 1
fi
