#!/bin/bash
cd -- "$(dirname -- "$0")" || exit 1
found=0
for candidate in python3.14 python3.13 python3.12 /opt/homebrew/bin/python3 /usr/local/bin/python3 python3; do
    if "$candidate" -c 'import sys; sys.exit(sys.version_info < (3,12))' >/dev/null 2>&1; then
        found=1
        "$candidate" installer/install.py "$@"
        break
    fi
done
if [ "$found" = 0 ]; then
    echo 'Instale Python 3.12 ou superior e abra este arquivo novamente.'
    open 'https://www.python.org/downloads/macos/'
fi
read -r -p 'Pressione Enter para fechar...'
