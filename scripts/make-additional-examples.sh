#!/bin/bash

bash_source_dir=$( cd "$(dirname "${BASH_SOURCE[0]}")" ; pwd -P )
doc_builder_dir="$bash_source_dir/../documentation_builder"

cd $doc_builder_dir
cd notebooks

jupyter nbconvert --to notebook --execute ./workflows/*.ipynb  --inplace --ExecutePreprocessor.timeout=-1
jupyter nbconvert --to notebook --execute ./advanced_visualization/*.ipynb  --inplace --ExecutePreprocessor.timeout=-1