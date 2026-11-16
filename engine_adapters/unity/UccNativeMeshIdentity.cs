using System;
using System.IO;
using System.Security.Cryptography;
using System.Text;
using UnityEngine;

namespace Ucc.UnityAdapter {
 public static class UccNativeMeshIdentity {
  public const string Policy="UCC_UNITY_NATIVE_MESH_ID_V1";
  public static string Hash(byte[] bytes) {
   using(var algorithm=SHA256.Create())return BitConverter.ToString(algorithm.ComputeHash(bytes)).Replace("-","").ToLowerInvariant();
  }
  static void Number(BinaryWriter writer,float value) {
   if(float.IsNaN(value)||float.IsInfinity(value))throw new InvalidDataException("Nonfinite native mesh value");writer.Write(value);
  }
  static void Vector(BinaryWriter writer,Vector3 value){Number(writer,value.x);Number(writer,value.y);Number(writer,value.z);}
  public static string Compute(SkinnedMeshRenderer source) {
   if(source==null||source.sharedMesh==null||!source.sharedMesh.isReadable)throw new InvalidDataException("Readable native source mesh required");
   var mesh=source.sharedMesh;int count=mesh.vertexCount;
   if(source.bones.Length!=163||mesh.bindposes.Length!=163||mesh.blendShapeCount!=12)throw new InvalidDataException("MPFB human bones, bind poses or facial shapes differ from the admitted profile");
   if(count<4||count>200000||mesh.subMeshCount!=1)throw new InvalidDataException("Unsupported native mesh size or materials");
   var positions=mesh.vertices;var normals=mesh.normals;var tangents=mesh.tangents;var uv=mesh.uv;
   if(normals.Length!=count||tangents.Length!=count||uv.Length!=count)throw new InvalidDataException("Native position/normal/tangent/UV coverage differs");
   using(var stream=new MemoryStream())using(var writer=new BinaryWriter(stream,new UTF8Encoding(false,true))) {
    writer.Write(Policy);writer.Write(count);writer.Write((int)mesh.indexFormat);writer.Write(mesh.subMeshCount);
    for(int i=0;i<count;i++) {
     Vector(writer,positions[i]);Vector(writer,normals[i]);Number(writer,tangents[i].x);Number(writer,tangents[i].y);Number(writer,tangents[i].z);Number(writer,tangents[i].w);
     Number(writer,uv[i].x);Number(writer,uv[i].y);
    }
    var triangles=mesh.triangles;writer.Write(triangles.Length);
    foreach(int index in triangles){if(index<0||index>=count)throw new InvalidDataException("Invalid native triangle index");writer.Write(index);}
    using(var counts=mesh.GetBonesPerVertex())using(var weights=mesh.GetAllBoneWeights()) {
     if(counts.Length!=count)throw new InvalidDataException("Missing native influence counts");
     writer.Write(counts.Length);int offset=0;
     foreach(byte n in counts) {
      if(n<1||n>8)throw new InvalidDataException("Native skin must retain one to eight influences");writer.Write(n);double sum=0;
      for(int k=0;k<n;k++) {
       if(offset>=weights.Length)throw new InvalidDataException("Native influence storage truncated");var weight=weights[offset++];
       if(weight.boneIndex<0||weight.boneIndex>=source.bones.Length||!(weight.weight>0))throw new InvalidDataException("Invalid native positive bone influence");
       writer.Write(weight.boneIndex);Number(writer,weight.weight);sum+=weight.weight;
      }
      if(Math.Abs(sum-1)>1e-6)throw new InvalidDataException("Native influences do not sum to one");
     }
     if(offset!=weights.Length)throw new InvalidDataException("Unexpected native influence tail");
    }
    writer.Write(mesh.bindposes.Length);
    foreach(var matrix in mesh.bindposes)for(int r=0;r<4;r++)for(int c=0;c<4;c++)Number(writer,matrix[r,c]);
    writer.Write(source.bones.Length);
    foreach(var bone in source.bones){if(bone==null)throw new InvalidDataException("Missing native bone");writer.Write(bone.name);writer.Write(bone.parent==null?"":bone.parent.name);}
    writer.Write(mesh.blendShapeCount);
    var dv=new Vector3[count];var dn=new Vector3[count];var dt=new Vector3[count];
    for(int key=0;key<mesh.blendShapeCount;key++) {
     if(mesh.GetBlendShapeFrameCount(key)!=1)throw new InvalidDataException("Unsupported native facial shape frames");
     writer.Write(mesh.GetBlendShapeName(key));Number(writer,mesh.GetBlendShapeFrameWeight(key,0));
     mesh.GetBlendShapeFrameVertices(key,0,dv,dn,dt);
     for(int v=0;v<count;v++){Vector(writer,dv[v]);Vector(writer,dn[v]);Vector(writer,dt[v]);}
    }
    writer.Flush();return Hash(stream.ToArray());
   }
  }
 }
}
