"""Fixed-profile finite bind math; no engine, Blender, Qt or private-data imports."""
from collections import Counter,defaultdict
from collections.abc import Callable
from fractions import Fraction
from itertools import product
import hashlib
import math
import struct
from .unreal_native_data import require,finite,integer,f32

IDENTITY = tuple(tuple(float(i == j) for j in range(4)) for i in range(4))


def expected_bone_name(source: str) -> str:
    """Legacy FBX import's verified namespace, punctuation and space rules."""
    name = source.rsplit(':', 1)[-1]
    for character in '.,/`%':
        name = name.replace(character, '_')
    return name.strip().replace(' ', '-')


def matrix(values):
    require(len(values) == 16, "matrix dimensions differ")
    return tuple(tuple(finite(values[i*4+j]) for j in range(4)) for i in range(4))


def transpose(a):
    return tuple(zip(*a))


def multiply(a, b):
    return tuple(tuple(sum(a[i][k]*b[k][j] for k in range(4)) for j in range(4)) for i in range(4))


def point(a, p):
    return tuple(sum(a[i][j] * p[j] for j in range(3)) + a[i][3] for i in range(3))


def inverse(a):
    rows = [list(a[i]) + list(IDENTITY[i]) for i in range(4)]
    for column in range(4):
        pivot = max(range(column, 4), key=lambda i: abs(rows[i][column]))
        require(abs(rows[pivot][column]) > 1e-15, "matrix is singular")
        rows[column], rows[pivot] = rows[pivot], rows[column]
        divisor = rows[column][column]
        rows[column] = [x / divisor for x in rows[column]]
        for row in range(4):
            if row != column:
                multiplier = rows[row][column]
                rows[row] = [x - multiplier*y for x, y in zip(rows[row], rows[column])]
    return tuple(tuple(row[4:]) for row in rows)


def quaternion_trs(values):
    require(len(values) == 10, "TRS dimensions differ")
    x, y, z, w, tx, ty, tz, sx, sy, sz = map(finite, values)
    return ((sx*(1-2*(y*y+z*z)), sy*2*(x*y-z*w), sz*2*(x*z+y*w), tx),
            (sx*2*(x*y+z*w), sy*(1-2*(x*x+z*z)), sz*2*(y*z-x*w), ty),
            (sx*2*(x*z-y*w), sy*2*(y*z+x*w), sz*(1-2*(x*x+y*y)), tz),
            (0, 0, 0, 1))

def expected_uv(uv):
    require(len(uv) == 2, "source UV dimension differs")
    return (f32(uv[0]), f32(1.0 - f32(uv[1])))


def expected_position_cm(point):
    """Declared -X/Z profile; caller verifies the closed profile and input seals."""
    require(len(point) == 3, "source point dimension differs")
    x, y, z = map(finite, point)
    return (-100.0 * y, -100.0 * x, 100.0 * z)


def unique_correspondence(source_points_cm, native_points_cm, cap_cm=0.0002, *, check=None):
    guard = check or (lambda: None)
    guard()
    require(0 < cap_cm <= 0.0002, "correspondence cap exceeds predeclared2um")
    buckets = {}
    cell = lambda p: tuple(math.floor(finite(x) / cap_cm) for x in p)
    for index, point in enumerate(source_points_cm):
        if index % 256 == 0: guard()
        require(len(point) == 3, "source position dimension differs")
        buckets.setdefault(cell(point), []).append(index)
    result, covered, maximum = [], set(), 0.0
    for ordinal, point in enumerate(native_points_cm):
        if ordinal % 128 == 0: guard()
        require(len(point) == 3, "native position dimension differs")
        key = cell(point)
        matches = []
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                for dz in (-1, 0, 1):
                    for ordinal, index in enumerate(buckets.get((key[0]+dx, key[1]+dy, key[2]+dz), ())):
                        if ordinal % 256 == 0: guard()
                        distance = math.dist(source_points_cm[index], point)
                        if distance <= cap_cm:
                            matches.append((index, distance))
        require(len(matches) == 1, "native correspondence is absent or ambiguous")
        index, distance = matches[0]
        result.append(index)
        covered.add(index)
        maximum = max(maximum, distance)
    require(len(covered) == len(source_points_cm), "native correspondence omits source vertex")
    return result, maximum


def oriented_key(corners):
    require(len(corners) == 3, "triangle corner count differs")
    corners = tuple(corners)
    return min(corners, corners[1:] + corners[:1], corners[2:] + corners[:2])

def uv_bits(uv):
    return tuple(struct.unpack("<II", struct.pack("<ff", *uv)))


def geometry(source: dict, native: dict, *, check=None) -> tuple[list[int], dict]:
    guard = check or (lambda: None)
    guard()
    points = [expected_position_cm(row) for row in source["vertices"]]
    mapping, error = unique_correspondence(points, native["positions"], check=guard)
    require(len(source["triangles"]) == len(source["corners"]), "source corner triangle count differs")
    expected = Counter()
    for triangle, corners in zip(source["triangles"], source["corners"]):
        require(corners["vertices"] == triangle and len(corners["uv"]) == 3,
                "source triangle/corner identities differ")
        expected[oriented_key(tuple((index, *uv_bits(expected_uv(uv)))
                                    for index, uv in zip(triangle, corners["uv"])))] += 1
    actual = Counter()
    indices = native["indices"]
    for start in range(0, len(indices), 3):
        if start % 384 == 0: guard()
        actual[oriented_key(tuple((mapping[index], *uv_bits(native["uv0"][index]))
                                  for index in indices[start:start + 3]))] += 1
    require(actual == expected, "native oriented triangles/exact UV corners differ from source")
    return mapping, {"source_vertices": len(points), "native_vertices": len(mapping),
                     "source_triangles": len(source["triangles"]),
                     "native_triangles": len(indices) // 3,
                     "maximum_correspondence_error_cm": error,
                     "oriented_triangle_and_float32_uv_corner_multiset_exact": True}


def morphs(source: dict, native: dict, mapping: list[int], *, check=None) -> dict:
    guard = check or (lambda: None)
    guard()
    expected = source["morphs"]
    require(set(expected) == set(native["morphs"]), "native morph identity set differs")
    maximum = 0.0
    observed_sparse = 0
    for name, source_deltas in expected.items():
        guard()
        require(len(source_deltas) == len(source["vertices"]), "source morph domain differs")
        native_deltas = native["morphs"][name]
        observed_sparse += len(native_deltas)
        for vertex, source_vertex in enumerate(mapping):
            if vertex % 128 == 0: guard()
            target = expected_position_cm(source_deltas[source_vertex])
            actual = native_deltas.get(vertex, (0.0, 0.0, 0.0))
            error = math.dist(target, actual)
            maximum = max(maximum, error)
            require(error <= 0.0001, "native morph position exceeds predeclared1um cap")
    return {"morph_names_exact": True, "morph_count": len(expected),
            "native_sparse_delta_count": observed_sparse, "maximum_morph_error_cm": maximum,
            "omitted_native_deltas_checked_as_zero": True}


def bone_identities(source: dict, native: dict, name_map: dict, *, check=None) -> dict:
    guard = check or (lambda: None)
    guard()
    source_bones = source["bones"]
    require(source['expected_unreal_bone_order']==[bone['name'] for bone in native['bones']],
            'native bone order differs from predeclared source FBX hierarchy order')
    require(set(name_map) == {bone["name"] for bone in source_bones}, "declared bone map domain differs")
    require(len(set(name_map.values())) == len(name_map), "declared bone name map is not bijective")
    expected_parent = {}
    for row in source_bones:
        expected_parent[name_map[row["name"]]] = None if row["parent"] is None else name_map[row["parent"]]
    require({bone["name"] for bone in native["bones"]} == set(expected_parent),
            "native canonical bone identity set differs")
    for bone in native["bones"]:
        parent = None if bone["parent"] == -1 else native["bones"][bone["parent"]]["name"]
        require(parent == expected_parent[bone["name"]], "native canonical bone hierarchy differs")
    return {"bone_count": len(source_bones), "declared_canonical_name_bijection_exact": True,
            "native_parent_names_exact": True}


def positive_weight_identities(source: dict, native: dict, mapping: list[int], name_map: dict, *, check=None) -> dict:
    guard = check or (lambda: None)
    guard()
    native_names = [bone["name"] for bone in native["bones"]]
    identities = 0
    for vertex, source_vertex in enumerate(mapping):
        if vertex % 128 == 0: guard()
        rows = source["weights"][source_vertex]
        require(len({name for name, _ in rows}) == len(rows), "source weight identity duplicated")
        total = sum(finite(weight) for _, weight in rows)
        require(total > 0 and all(weight > 0 for _, weight in rows), "source weight positive domain differs")
        expected = {name_map[name] for name, _ in rows}
        actual = {native_names[bone] for bone, _ in native["influences"][vertex]}
        require(expected == actual, "native positive weight identity differs from source")
        identities += len(actual)
    return {"all_positive_weight_identities_exact_on_every_native_split": True,
            "native_positive_identity_count_including_splits": identities,
            "numeric_weight_residuals_computed": False,
            "numeric_weight_admission": "INDEPENDENT_NUMERIC_GATE_REQUIRED"}

H = ((1,0,0,0),(0,-1,0,0),(0,0,1,0),(0,0,0,1))


R = ((0,-1,0,0),(1,0,0,0),(0,0,1,0),(0,0,0,1))


U = ((100,0,0,0),(0,100,0,0),(0,0,100,0),(0,0,0,1))


WITNESSES = ((0,0,0),(1,0,0),(0,1,0),(0,0,1))


def expected_global(original_world):
    # Right H is the UE local-frame handedness conjugation. U scales ALL
    # three world rows, not translation alone, as proved before character use.
    return multiply(multiply(multiply(multiply(U,H),R),matrix(original_world)),H)


def verify_bind(source: dict, native: dict, name_map: dict, *, check=None) -> dict:
    guard = check or (lambda: None)
    guard()
    identities = bone_identities(source,native,name_map,check=guard)
    expected = {name_map[row['name']]:expected_global(row['world']) for row in source['bones']}
    globals_ = []
    head_max = frame_max = inverse_max = 0.0
    for index,bone in enumerate(native['bones']):
        if index % 128 == 0: guard()
        local=quaternion_trs(bone['local_trs_float64_quaternion_xyzw_translation_scale'])
        actual=local if bone['parent']==-1 else multiply(globals_[bone['parent']],local)
        globals_.append(actual)
        target=expected[bone['name']]
        observed_inverse=transpose(matrix(native['inverse_bind_matrices'][index]))
        for witness in WITNESSES:
            expected_world=point(target,witness)
            error=math.dist(point(actual,witness),expected_world)
            if witness==(0,0,0):
                head_max=max(head_max,error)
                require(error<=0.0002,'native full bind head exceeds predeclared2um cap')
            else:
                frame_max=max(frame_max,error)
                require(error<=0.005,'native full bind basis endpoint exceeds predeclared50um rest cap')
            expected_from_native_inverse=point(target,point(observed_inverse,expected_world))
            inverse_error=math.dist(expected_from_native_inverse,expected_world)
            inverse_max=max(inverse_max,inverse_error)
            require(inverse_error<=0.005,'native inverse bind source witness exceeds predeclared50um rest cap')
    return {**identities,'full_bind_basis_witnesses_per_bone':4,
            'maximum_native_full_bind_head_error_cm':head_max,
            'maximum_native_full_bind_basis_endpoint_error_cm':frame_max,
            'maximum_native_inverse_bind_source_witness_error_cm':inverse_max,
            'source_derived_full_bind_and_inverse_bind':True,
            'bone_head_cap_cm':0.0002,'basis_and_inverse_world_witness_cap_cm':0.005,
            'expected_column_formula':'U100 * H * Rz90 * B_original * H'}

def canonical_corners(corners,normals):
    start=min(range(3),key=lambda index:tuple(corners[index:]+corners[:index]))
    return tuple(corners[start:]+corners[:start]),normals[start:]+normals[:start]


def unit(row):
    values=tuple(map(finite,row));length=math.sqrt(sum(v*v for v in values))
    require(length>1e-12,'native/source normal has zero length')
    return tuple(v/length for v in values)


def angle(a,b):
    a=unit(a);b=unit(b)
    return math.degrees(math.acos(max(-1.0,min(1.0,sum(x*y for x,y in zip(a,b))))))


def verify_corner_normals(source: dict, native: dict, mapping: list[int], raw: bytes, *, check=None) -> dict:
    guard = check or (lambda: None)
    guard()
    triangles=source['triangles'];expected_bytes=len(triangles)*3*12
    require(len(raw)==expected_bytes,'source original corner-normal byte domain differs')
    source_normals=list(struct.iter_unpack('<fff',raw))
    expected=defaultdict(list);actual=defaultdict(list)
    for index,corners in enumerate(source['corners']):
        if index % 128 == 0: guard()
        keys=[(vertex,*uv_bits(expected_uv(uv))) for vertex,uv in zip(corners['vertices'],corners['uv'])]
        vectors=[]
        for nx,ny,nz in source_normals[index*3:index*3+3]:
            normal=unit((nx,ny,nz))
            vectors.append((-normal[1],-normal[0],normal[2]))
        key,vectors=canonical_corners(keys,vectors);expected[key].append(vectors)
    indices=native['indices']
    for start in range(0,len(indices),3):
        if start % 384 == 0: guard()
        row=indices[start:start+3]
        keys=[(mapping[index],*uv_bits(native['uv0'][index])) for index in row]
        vectors=[native['normals'][index] for index in row]
        key,vectors=canonical_corners(keys,vectors);actual[key].append(vectors)
    require(set(actual)==set(expected),'normal source/native oriented corner identities differ')
    maximum=0.0
    for key,targets in expected.items():
        guard()
        observed=actual[key]
        require(len(targets)==len(observed) and len(targets)<=64,'normal triangle multiplicity differs or exceeds cap')
        errors=[[max(angle(a,b) for a,b in zip(target,row)) for row in observed] for target in targets]
        matched={}
        def assign(target,seen):
            for item,error in enumerate(errors[target]):
                if error<=0.5 and item not in seen:
                    seen.add(item)
                    if item not in matched or assign(matched[item],seen):
                        matched[item]=target;return True
            return False
        require(all(assign(target,set()) for target in range(len(targets))),
                'native bind corner normal exceeds predeclared0.5degree cap')
        maximum=max(maximum,*(errors[target][item] for item,target in matched.items()))
    return {'native_bind_corner_normals_finite_within_predeclared_quality_cap':True,
            'normal_angle_cap_degrees':0.5,'maximum_normal_angle_degrees':maximum,
            'source_corner_normals_sha256':hashlib.sha256(raw).hexdigest(),
            'corner_count':len(source_normals),'stronger_component_or_ISA_bound_verified':False}

Q=65535

def verify_numeric_weights(source: dict, native: dict, mapping: list[int], name_map: dict, *, check=None) -> dict:
    guard = check or (lambda: None)
    guard()
    names=[row['name'] for row in native['bones']]
    maximum=Fraction(0);checked=violations=0;double_sum_exact=True
    for vertex,source_vertex in enumerate(mapping):
        if vertex % 128 == 0: guard()
        rows=source['weights'][source_vertex]
        require(1<=len(rows)<=8,'source numeric weight count outside declared max8')
        require(all(finite(weight)>0 and f32(weight)==weight for _,weight in rows),
                'source weights are not positive exact float32')
        fractions=[(name_map[name],Fraction.from_float(float(weight))) for name,weight in rows]
        total=sum((weight for _,weight in fractions),Fraction(0))
        double_sum_exact &= Fraction.from_float(sum(float(weight) for _,weight in rows))==total
        expected={name:weight/total for name,weight in fractions}
        actual={names[bone]:Fraction(raw,Q) for bone,raw in native['influences'][vertex]}
        require(set(actual)==set(expected),'native numeric weight bone identities differ')
        require(sum(actual.values(),Fraction(0))==1,'native numeric weights do not sum exactly1')
        cap=Fraction(len(rows)+2,Q)+Fraction(32,2**24)
        for name,value in expected.items():
            error=abs(actual[name]-value)
            maximum=max(maximum,error);checked+=1
            violations+=int(error>cap)
    return {'passed':violations==0,'all_native_split_positive_weights_checked':checked,
            'violating_weight_count':violations,'maximum_normalized_weight_error':float(maximum),
            'source_reference_comparison':'original exact_float32 weights normalized by exact sum; equivalent float64 ratios',
            'source_group_float64_sums_exact':double_sum_exact,
            'comparison_arithmetic':'exact rational; no floating-point threshold decision',
            'predeclared_cap':'(source_positive_count+2)/65535 + 32*2^-24',
            'cap_selected_from_observation':False,'scope':'finite private character under primary-locked declared stock precise profile',
            'arbitrary_fastmath_or_all_compiler_guarantee':False}
