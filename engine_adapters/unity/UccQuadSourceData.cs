using System;
using System.IO;
using System.Linq;
using System.Collections.Generic;
using System.Text.RegularExpressions;
using UnityEngine;

namespace Ucc.UnityAdapter {
 [Serializable] public struct UccQuad {public int a,b,c,d;public int At(int i){return i==0?a:i==1?b:i==2?c:d;}}
 [Serializable] public struct UccCorner {public int face,corner;}
 [Serializable] public sealed class UccQuadSourceData {
  public int schema_version,source_vertices,native_vertices;
  public string policy,rig_family,master_sha256,native_mesh_sha256;
  public int[] native_source;public UccQuad[] quads;public string[] bone_names,shape_names;
  public int[] FirstNative,Offsets;public UccCorner[] Adjacency;
  public static UccQuadSourceData Read(TextAsset asset,string expectedSha,SkinnedMeshRenderer source) {
   if(source==null||source.sharedMesh==null||source.bones.Length!=163||source.bones.Any(b=>b==null))throw new InvalidDataException("Native mesh or MPFB human bones are missing");
   var sha=new Regex("^[0-9a-f]{64}$");
   if(asset==null||asset.bytes.Length<1||asset.bytes.Length>8*1024*1024||expectedSha==null||!sha.IsMatch(expectedSha)||UccNativeMeshIdentity.Hash(asset.bytes)!=expectedSha)
    throw new InvalidDataException("Unity source topology is absent, too large or no longer SHA-bound");
   var value=JsonUtility.FromJson<UccQuadSourceData>(asset.text);
   if(value==null||value.schema_version!=1||value.policy!="UCC_UNITY_SOURCE_QUAD_NORMALS_V1"||value.rig_family!="MPFB_HUMAN_V1"
      ||value.master_sha256==null||!sha.IsMatch(value.master_sha256)||value.native_mesh_sha256==null||!sha.IsMatch(value.native_mesh_sha256))
    throw new InvalidDataException("Unsupported source topology version, family or identities");
   if(value.source_vertices<4||value.source_vertices>100000||value.native_vertices<value.source_vertices||value.native_vertices>200000
      ||value.native_source==null||value.native_source.Length!=value.native_vertices||source.sharedMesh.vertexCount!=value.native_vertices
      ||value.quads==null||value.quads.Length<1||value.quads.Length>200000)
    throw new InvalidDataException("Source/native topology counts differ");
   if(value.bone_names==null||value.bone_names.Length!=163||!value.bone_names.SequenceEqual(source.bones.Select(b=>b.name))
      ||value.bone_names.Distinct().Count()!=163||value.shape_names==null||value.shape_names.Length!=12||value.shape_names.Distinct().Count()!=12
      ||source.sharedMesh.blendShapeCount!=12||!value.shape_names.SequenceEqual(Enumerable.Range(0,12).Select(source.sharedMesh.GetBlendShapeName))
      ||value.shape_names.Any(name=>name==null||!name.StartsWith("UCC_EXPR_V1_",StringComparison.Ordinal)))
    throw new InvalidDataException("MPFB human bone or expression identities changed");
   if(UccNativeMeshIdentity.Compute(source)!=value.native_mesh_sha256)throw new InvalidDataException("Native mesh/skin/UV/morph/bind identity changed");
   for(int key=0;key<12;key++)if(source.sharedMesh.GetBlendShapeFrameWeight(key,0)!=100)throw new InvalidDataException("Unsupported native expression frame scale");
   value.FirstNative=Enumerable.Repeat(-1,value.source_vertices).ToArray();
   for(int v=0;v<value.native_vertices;v++){int original=value.native_source[v];if(original<0||original>=value.source_vertices)throw new InvalidDataException("Invalid source vertex identity");if(value.FirstNative[original]<0)value.FirstNative[original]=v;}
   if(value.FirstNative.Any(v=>v<0))throw new InvalidDataException("Native vertices omit source coverage");
   var rows=Enumerable.Range(0,value.source_vertices).Select(i=>new List<UccCorner>()).ToArray();
   var faces=new HashSet<string>();var edges=new Dictionary<ulong,int>();
   for(int f=0;f<value.quads.Length;f++) {
    var q=value.quads[f];var ids=new[]{q.a,q.b,q.c,q.d};
    if(ids.Any(v=>v<0||v>=value.source_vertices)||ids.Distinct().Count()!=4)throw new InvalidDataException("Malformed original quad");
    var sorted=(int[])ids.Clone();Array.Sort(sorted);if(!faces.Add(String.Join(",",sorted)))throw new InvalidDataException("Repeated original quad");
    for(int c=0;c<4;c++) {
     int a=ids[c],b=ids[(c+1)%4];rows[a].Add(new UccCorner{face=f,corner=c});
     if(rows[a].Count>32)throw new InvalidDataException("Source valence exceeds the bounded GPU work budget");
     ulong key=((ulong)Math.Min(a,b)<<32)|(uint)Math.Max(a,b);int direction=a<b?1:-1;
     if(edges.TryGetValue(key,out var previous)){if(previous==0||previous==direction)throw new InvalidDataException("Nonmanifold or inconsistent original winding");edges[key]=0;}
     else edges.Add(key,direction);
    }
   }
   if(rows.Any(row=>row.Count==0))throw new InvalidDataException("Loose source vertices have no admitted geometric normal");
   var flat=new List<UccCorner>();value.Offsets=new int[value.source_vertices+1];
   for(int v=0;v<rows.Length;v++){value.Offsets[v]=flat.Count;flat.AddRange(rows[v]);}value.Offsets[value.source_vertices]=flat.Count;value.Adjacency=flat.ToArray();
   return value;
  }
 }
}
