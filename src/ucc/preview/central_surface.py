"""Complete trunk crossing identities against independently verified skin caches."""
from dataclasses import dataclass
from hashlib import sha256
import struct

from ucc.animations.source_rest_frames import is_sha256
from ucc.core.errors import ValidationError
from .central_scope import checked_ids
from .contact_areas import polygon_membership
from .surface_review import SurfaceReview

POLICY='MEASURED_COMPLETE_TRUNK_HAND_SURFACES_V1'


@dataclass(frozen=True,slots=True)
class CompleteSurfaceVariant:
    surface: SurfaceReview
    hand_polygons: tuple[tuple[frozenset[int],frozenset[int]],...]
    body_polygons: tuple[tuple[frozenset[int],frozenset[int]],...]


def _parse_variant(data,cache,volume,polygons,*,cancel_check=lambda:None):
    """Parse after fresh receipt and the corresponding enclosure are validated.

    This helper verifies selection, full coverage and stable identities. It
    cannot establish physical pairs from a digest; the coordinator must bind
    the complete report to independently reproduced saved-Action evidence.
    """
    if (type(data) is not dict or set(data)!={'frames'} or type(data['frames']) is not list or
        len(data['frames'])!=cache.frame_count or len(volume['frames'])!=cache.frame_count):
        raise ValidationError('Complete trunk surfaces require every verified source frame')
    membership=polygon_membership(polygons,cache.vertex_count)
    highlights=[];pairs=[];hashes=[];hand_polygons=[];body_polygons=[];total=0
    for index,(row,reference) in enumerate(zip(data['frames'],volume['frames'])):
        cancel_check()
        if (type(row) is not dict or set(row)!={'frame','skin_sha256','triangle_sha256','observation'} or
            type(row['frame']) is not int or row['frame']!=index+1 or
            any(row[k]!=reference[k] for k in ('frame','skin_sha256','triangle_sha256'))):
            raise ValidationError('Complete trunk surface pose/skin/topology differs')
        _,indices=cache.frame(index)
        if sha256(indices).hexdigest()!=row['triangle_sha256']:
            raise ValidationError('Complete trunk surface triangle buffer differs')
        observation=row['observation'];expected=reference['observation']
        if (type(observation) is not dict or set(observation)!={'body_triangle_ids','left','right'} or
            observation['body_triangle_ids']!=expected['body_triangle_ids']):
            raise ValidationError('Complete trunk surface body selection differs')
        body_ids=checked_ids(observation['body_triangle_ids'],cache.triangle_count,nonempty=True)
        ids=set();counts=[];hands=[];bodies=[]
        for side in ('left','right'):
            hit=observation[side]
            fields={'pair_count','pair_sha256','hand_triangles','central_triangles',
                    'selected_hand_triangles','hand_polygons','body_polygons'}
            if (type(hit) is not dict or set(hit)!=fields or type(hit['pair_count']) is not int or
                not 0<=hit['pair_count']<=250000 or not is_sha256(hit['pair_sha256']) or
                hit['selected_hand_triangles']!=expected[side]['selected_triangles']):
                raise ValidationError('Invalid complete trunk hand pair record')
            selected=checked_ids(hit['selected_hand_triangles'],cache.triangle_count,nonempty=True,limit=10000)
            hand=checked_ids(hit['hand_triangles'],cache.triangle_count)
            body=checked_ids(hit['central_triangles'],cache.triangle_count)
            count=hit['pair_count']
            if (selected&body_ids or len(selected)*len(body_ids)>40000000 or not hand<=selected or not body<=body_ids or
                any(len(value)>count or bool(value)!=bool(count) for value in (hand,body)) or
                count>len(hand)*len(body) or ((not count)!=(hit['pair_sha256']==sha256().hexdigest()))):
                raise ValidationError('Complete trunk pair count, workload or region identity differs')
            def stable_polygons(triangles):
                result=set()
                for n,triangle in enumerate(sorted(triangles)):
                    if n%256==0:cancel_check()
                    vertices=struct.unpack_from('<III',indices,triangle*12)
                    candidates=set.intersection(*(membership.get(v,set()) for v in vertices))
                    if len(candidates)!=1:raise ValidationError('Complete trunk highlight lacks one actual polygon')
                    result.update(candidates)
                return result
            hand_faces=checked_ids(hit['hand_polygons'],len(polygons))
            body_faces=checked_ids(hit['body_polygons'],len(polygons))
            if hand_faces!=stable_polygons(hand) or body_faces!=stable_polygons(body):
                raise ValidationError('Complete trunk stable polygon identity differs')
            hands.append(frozenset(hand_faces));bodies.append(frozenset(body_faces));counts.append(count)
            ids.update(hand|body);total+=len(hand)+len(body)
        highlights.append(tuple(sorted(ids)));pairs.append(tuple(counts));hashes.append(row['triangle_sha256'])
        hand_polygons.append(tuple(hands));body_polygons.append(tuple(bodies))
    if total>1000000:raise ValidationError('Complete trunk highlight budget exceeded')
    surface=SurfaceReview('CHECKED','',tuple(highlights),tuple(pairs),tuple(hashes),POLICY)
    return CompleteSurfaceVariant(surface,tuple(hand_polygons),tuple(body_polygons))
