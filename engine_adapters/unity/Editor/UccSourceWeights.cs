using System;
using System.IO;
using System.Linq;
using System.Collections.Generic;
using UnityEngine;
using UnityEditor;
using Unity.Collections;

namespace Ucc.UnityAdapter.Editor {
 // Explicit import-stage conversion. Never called by runtime or saved-scene verification.
 public static class UccSourceWeights {
  [Serializable] public sealed class Weight { public string bone; public float weight; }
  [Serializable] public sealed class Vertex { public Vector3 position; public Weight[] weights; }
  [Serializable] public sealed class Source {
   public int schema_version; public string policy; public string master_sha256;
   public string request_sha256; public Vertex[] vertices;
  }
  static bool Finite(float value) {return !float.IsNaN(value)&&!float.IsInfinity(value);}
  static bool Digest(string value) {return value!=null&&value.Length==64&&value.All(c=>(c>='0'&&c<='9')||(c>='a'&&c<='f'));}
  static (int,int,int) Cell(Vector3 point) {
   if(!Finite(point.x)||!Finite(point.y)||!Finite(point.z)||point.sqrMagnitude>10000)
    throw new InvalidDataException("Source correspondence requires finite bind positions within 100 metres");
   return ((int)Math.Floor(point.x*10000),(int)Math.Floor(point.y*10000),(int)Math.Floor(point.z*10000));
  }
  public static int[] Apply(SkinnedMeshRenderer renderer,string sourcePath,string fileSha,
                            string masterSha,string requestSha,string target) {
   if(!Digest(fileSha)||!Digest(masterSha)||!Digest(requestSha))throw new InvalidDataException("Missing source-weight hash bindings");
   var file=new FileInfo(sourcePath);
   if(!file.Exists||file.Length<2||file.Length>8*1024*1024||(file.Attributes&FileAttributes.ReparsePoint)!=0)
    throw new InvalidDataException("Source weights missing, redirected or oversized");
   byte[] bytes=File.ReadAllBytes(sourcePath);
   if(UccNativeMeshIdentity.Hash(bytes)!=fileSha)throw new InvalidDataException("Source-weight bytes differ from the reviewed hash");
   var source=JsonUtility.FromJson<Source>(System.Text.Encoding.UTF8.GetString(bytes));
   if(source==null||source.schema_version!=1||source.policy!="UCC_UNITY_SOURCE_WEIGHTS_V1"||
      source.master_sha256!=masterSha||source.request_sha256!=requestSha||source.vertices==null||source.vertices.Length!=13380)
    throw new InvalidDataException("Source weights differ from the admitted master/request/profile");
   if(renderer==null||renderer.sharedMesh==null||!renderer.sharedMesh.isReadable||renderer.bones.Length!=163||
      renderer.sharedMesh.vertexCount<13380||renderer.sharedMesh.vertexCount>200000)
    throw new InvalidDataException("Readable MPFB human native skin required");
   if(target!="Assets/UCC/CharacterSkin.asset"||File.Exists(target)||AssetDatabase.LoadMainAssetAtPath(target)!=null)
    throw new InvalidDataException("Refuse replacing or redirecting a native mesh asset");
   var bones=new Dictionary<string,int>(StringComparer.Ordinal);
   for(int i=0;i<renderer.bones.Length;i++) {
    var bone=renderer.bones[i];
    if(bone==null||String.IsNullOrWhiteSpace(bone.name)||bones.ContainsKey(bone.name))throw new InvalidDataException("Missing or duplicate source family bone");
    bones.Add(bone.name,i);
   }
   var buckets=new Dictionary<(int,int,int),List<int>>();
   for(int i=0;i<source.vertices.Length;i++) {
    var vertex=source.vertices[i];
    if(vertex==null||vertex.weights==null||vertex.weights.Length<1||vertex.weights.Length>8)
     throw new InvalidDataException("Unsupported source influence count");
    var unique=new HashSet<string>(StringComparer.Ordinal);double sum=0;
    foreach(var weight in vertex.weights) {
     if(weight==null||weight.bone==null||!bones.ContainsKey(weight.bone)||!unique.Add(weight.bone)||!Finite(weight.weight)||weight.weight<=0)
      throw new InvalidDataException("Invalid, missing or duplicate positive source bone influence");
     sum+=weight.weight;
    }
    if(Math.Abs(sum-1)>1e-6)throw new InvalidDataException("Nonunit source influences");
    var cell=Cell(vertex.position);
    if(!buckets.ContainsKey(cell))buckets[cell]=new List<int>();buckets[cell].Add(i);
   }
   var original=renderer.sharedMesh;var vertices=original.vertices;
   var counts=new byte[vertices.Length];var weights=new List<BoneWeight1>();
   var mapping=new int[vertices.Length];var coverage=new HashSet<int>();
   for(int i=0;i<vertices.Length;i++) {
    var point=renderer.localToWorldMatrix.MultiplyPoint3x4(vertices[i]);var cell=Cell(point);int match=-1;
    for(int x=-1;x<=1;x++)for(int y=-1;y<=1;y++)for(int z=-1;z<=1;z++) {
     if(!buckets.TryGetValue((cell.Item1+x,cell.Item2+y,cell.Item3+z),out var candidates))continue;
     foreach(int index in candidates)if(Vector3.Distance(point,source.vertices[index].position)<2e-6f) {
      if(match!=-1)throw new InvalidDataException("Ambiguous exact source/native vertex correspondence");match=index;
     }
    }
    if(match<0)throw new InvalidDataException("Missing exact source/native vertex correspondence");
    mapping[i]=match;coverage.Add(match);
    var row=source.vertices[match].weights.OrderByDescending(w=>w.weight).ThenBy(w=>w.bone,StringComparer.Ordinal).ToArray();
    counts[i]=(byte)row.Length;
    foreach(var weight in row)weights.Add(new BoneWeight1{boneIndex=bones[weight.bone],weight=weight.weight});
   }
   if(coverage.Count!=source.vertices.Length)throw new InvalidDataException("Incomplete source skin surface coverage");
   Mesh owned=null;bool saved=false;
   try {
    owned=UnityEngine.Object.Instantiate(original);owned.name="UCC_Source_Bound_Skin";
    using(var c=new NativeArray<byte>(counts,Allocator.Temp))
    using(var w=new NativeArray<BoneWeight1>(weights.ToArray(),Allocator.Temp))owned.SetBoneWeights(c,w);
    // Validate the actual native representation before making it a persistent asset.
    renderer.sharedMesh=owned;UccNativeMeshIdentity.Compute(renderer);renderer.sharedMesh=original;
    AssetDatabase.CreateAsset(owned,target);saved=true;AssetDatabase.SaveAssets();renderer.sharedMesh=owned;
    return mapping;
   } catch {
    renderer.sharedMesh=original;
    if(saved)AssetDatabase.DeleteAsset(target);
    else if(owned!=null)UnityEngine.Object.DestroyImmediate(owned);
    throw;
   }
  }
 }
}
