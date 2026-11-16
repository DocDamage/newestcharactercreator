"""Independent pinned expression admission; never imports the core recipe."""
from pathlib import Path

from blender_bridge.face_policy import BASE_SHA, RIG_SHA, digest, read_json

POLICY = 'BOUNDED_MPFB_EXPRESSION_UNITS_V1'
PREFIX = 'UCC_EXPR_V1_'
FAMILIES = ('african', 'asian', 'caucasian')
# role, family and the SHA of the already-installed MPFB 2.0.18 target bytes.
TARGETS = (
    ('eye_left_closure', 'african', '2d358745e955ead9d73f85ed224568a8d347f3f3b897c26cbd412faf2bfa9f3a'),
    ('eye_left_closure', 'asian', '0d52fee2d66b933ece83f3c7aa48e85bfe85e8adbed0931dbd37025866a1a67d'),
    ('eye_left_closure', 'caucasian', 'ff0d21ceb6da55fe51e03b48a7562a650924fea9bef0c686fcd7aa44d16422ed'),
    ('eye_right_closure', 'african', 'c1b0c3609d9fb59a97dabe8ace10622da58969f4566125b38f47285afef320d5'),
    ('eye_right_closure', 'asian', '0c99a5f559a1d67f630a329b9724fe3742a2c35709b8baa8a6d37903f35b9b77'),
    ('eye_right_closure', 'caucasian', '2b7be6bc65845d77e5f83b7bf852090854747e448644997795fa59b6cf76122d'),
    ('mouth_corners', 'african', '5560c685cd55ae6a00830e539ac54135cb4dcfec6a28be90510c931dcfdca478'),
    ('mouth_corners', 'asian', 'd881bb8feda2637bdaef2c7d7c6bed12f0be5914949e5a2cb9b06a583af412c0'),
    ('mouth_corners', 'caucasian', 'd881bb8feda2637bdaef2c7d7c6bed12f0be5914949e5a2cb9b06a583af412c0'),
    ('mouth_open', 'african', 'd710d4ae1693e7278a5bbe620276970fb6e89de139b50aaaea2830c31146459a'),
    ('mouth_open', 'asian', 'b52bbe631152844bb7b835c0f98d12ab0a1c0689e02e067b239d8349ccf9aab2'),
    ('mouth_open', 'caucasian', 'dc1260a8728d93a9c52d6b35b5f55ad39ab8096090acd5ccad7f973c26e28818'),
)


def filename(role: str, family: str) -> str:
    return 'expr-'+role+'-'+family+'.target.gz'


def keyname(role: str, family: str) -> str:
    return PREFIX+role+'_'+family


def recipe(raw: object, master_sha: str) -> dict:
    expected = {'schema_version': 1, 'policy': POLICY, 'family': 'humanoid.v1',
                'mpfb_version': '2.0.18', 'neutral': True,
                'bindings': {'master_sha256': master_sha, 'base_sha256': BASE_SHA, 'rig_sha256': RIG_SHA},
                'targets': [{'role': role, 'family': family, 'file': filename(role, family),
                             'key': keyname(role, family), 'sha256': sha} for role, family, sha in TARGETS]}
    if (type(raw) is not dict or type(raw.get('schema_version')) is not int
            or raw.get('neutral') is not True or raw != expected):
        raise ValueError('Expression recipe differs from the independent pinned neutral contract')
    return expected


def check_inputs(root: Path, options: dict, *, verify: bool = False) -> dict:
    names = {'candidate.blend': 'master_sha256', 'expression_recipe.json': 'recipe_sha256',
             **{filename(r, f): r+'_'+f+'_sha256' for r, f, _ in TARGETS}}
    if verify:
        names.update({'expression_human.blend': 'prepared_sha256',
                      'expression_report.json': 'report_sha256'})
    if (type(options) is not dict or set(options) != set(names.values()) or any(
            type(v) is not str or len(v) != 64 or any(c not in '0123456789abcdef' for c in v)
            for v in options.values())):
        raise ValueError('Expression worker requires all exact input identities')
    if any(options[r+'_'+f+'_sha256'] != sha for r, f, sha in TARGETS):
        raise ValueError('Expression worker target differs from pinned MPFB data')
    for name, field in names.items():
        path = root/name
        if path.is_symlink() or not path.is_file() or digest(path) != options[field]:
            raise ValueError('Changed expression input: '+name)
    return recipe(read_json(root/'expression_recipe.json', options['recipe_sha256']), options['master_sha256'])
