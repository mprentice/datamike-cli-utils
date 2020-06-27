# datamike-cli-utils

My helpful command-line utilities.

## Installation

Simple installation for this session:

    mkdir -p ~/.local
    cd ~/.local
    git clone https://github.com/mprentice/datamike-cli-utils.git
    export PATH="${HOME}/.local/datamike-cli-utils/bin:${PATH}"

For bash:

    echo 'export PATH="${HOME}/.local/datamike-cli-utils/bin:${PATH}"' >> ~/.bashrc

For zsh:

    echo 'export PATH="${HOME}/.local/datamike-cli-utils/bin:${PATH}"' >> ~/.zshenv

### Pre-requisites

`batchrename.py` and `genpassword.py` have no dependencies beyond the python3
standard library. Both require python3.

## Usage

### batchrename.py

    batchrename.py --help

### genpassword.py

    genpassword.py --help

## Tests

### batchrename.py

    batchrename.py --test

### genpassword.py

    genpassword.py --test
