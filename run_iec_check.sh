#!/bin/bash
docker run -it -v ./$1:/app/$1 iecc $1 
echo ""
