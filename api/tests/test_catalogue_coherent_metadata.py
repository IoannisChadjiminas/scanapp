from pathlib import Path
import hashlib
import sys
import numpy as np
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from prepare_catalogue_coherent_metadata import table_digest,vector_hashes


def test_digest_distinguishes_null_empty_and_c_order():
    contract=dict(keys=['id'],columns=['id','value'])
    a=[dict(id='é',value=None),dict(id='Z',value='')]
    assert table_digest(a,contract)==table_digest(list(reversed(a)),contract)
    assert table_digest(a,contract)!=table_digest([dict(id='é',value=''),a[1]],contract)


def test_vector_preservation_requires_exact_bytes_and_unique_ids():
    matrix=np.zeros((1,384),np.float32);matrix[0,0]=1
    parent={'c':hashlib.sha256(matrix[0].astype('>f4').tobytes()).hexdigest()}
    hashes,_=vector_hashes(matrix,['c'],parent);assert hashes==parent
    with pytest.raises(ValueError):vector_hashes(matrix,['x'],parent)
    with pytest.raises(ValueError):vector_hashes(np.concatenate([matrix,matrix]),['c','c'],parent)
    changed=matrix.copy();changed[0,0]=-1
    with pytest.raises(ValueError):vector_hashes(changed,['c'],parent)
