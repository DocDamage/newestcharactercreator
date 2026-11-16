using System;
using System.IO;
using System.Linq;
using UnityEngine;
using UnityEditor;

namespace Ucc.UnityAdapter.Editor {
 // Read-only native observations. Only the independent host admits source parity.
 public static class UccUnityObservation {
  [Serializable] public sealed class Weight {public int bone;public float weight;}
  [Serializable] public sealed class Bone {public string name,parent;public Vector3 position;}
  [Serializable] public sealed class Shape {public string name;public float frame_weight;public Vector3[] deltas;}
  [Serializable] public sealed class MaterialData {public string shader;public Color color;public float smoothness,metallic;public bool textures,property_block;public float mode;}
  [Serializable] public sealed class Profile {
   public string unity,color_space,skin_weights,renderer_quality;public int max_influences,animation_clips;
   public bool readable,offscreen,force_matrix_recalculation,import_animation,optimize_bones,bake_axis;
   public float minimum_weight;
  }
  [Serializable] public sealed class Observation {
   public int schema_version=1;public string policy="UCC_UNITY_NATIVE_BIND_OBSERVATION_V1";
   public string request_sha256,master_sha256,mode,native_mesh_sha256;
   public Profile profile;public Vector3[] vertices,baked;public Vector2[] uv;public int[] triangles,influences;
   public Weight[] weights;public string[] skin_bones;public Bone[] bones;public Shape[] shapes;public MaterialData material;
   public bool runtime_component_present,runtime_verified=false,visual_quality_approved=false;
  }
  public static Observation Read(GameObject root,string requestSha,string masterSha,string mode) {
   if(Application.isPlaying||root==null||root.scene.path!="Assets/UCC/Character.unity"||
      (mode!="stage"&&mode!="reopen"))throw new InvalidDataException("Native observation requires the actual saved character scene");
   var skins=root.GetComponentsInChildren<SkinnedMeshRenderer>(true);
   if(skins.Length!=1)throw new InvalidDataException("Native observation requires exactly one skin");
   var source=skins[0];var mesh=source.sharedMesh;
   string fingerprint=UccNativeMeshIdentity.Compute(source);
   var importer=AssetImporter.GetAtPath("Assets/UCC/character.fbx") as ModelImporter;
   if(importer==null||source.sharedMaterials.Length!=1||source.sharedMaterial==null)
    throw new InvalidDataException("Actual imported model/material missing");
   var world=source.localToWorldMatrix;var material=source.sharedMaterial;
   var shapes=new Shape[mesh.blendShapeCount];
   for(int key=0;key<shapes.Length;key++) {
    if(mesh.GetBlendShapeFrameCount(key)!=1)throw new InvalidDataException("Unsupported native facial frame count");
    var delta=new Vector3[mesh.vertexCount];mesh.GetBlendShapeFrameVertices(key,0,delta,null,null);
    shapes[key]=new Shape{name=mesh.GetBlendShapeName(key),frame_weight=mesh.GetBlendShapeFrameWeight(key,0),
                          deltas=delta.Select(v=>world.MultiplyVector(v)).ToArray()};
   }
   var baked=new Mesh();
   try {
    source.BakeMesh(baked,false);
    using(var counts=mesh.GetBonesPerVertex())using(var weights=mesh.GetAllBoneWeights()) {
     return new Observation{request_sha256=requestSha,master_sha256=masterSha,mode=mode,native_mesh_sha256=fingerprint,
      vertices=mesh.vertices.Select(v=>world.MultiplyPoint3x4(v)).ToArray(),
      baked=baked.vertices.Select(v=>world.MultiplyPoint3x4(v)).ToArray(),uv=mesh.uv,triangles=mesh.triangles,
      influences=counts.Select(v=>(int)v).ToArray(),weights=weights.Select(w=>new Weight{bone=w.boneIndex,weight=w.weight}).ToArray(),
      skin_bones=source.bones.Select(b=>b.name).ToArray(),shapes=shapes,
      bones=root.GetComponentsInChildren<Transform>(true).Select(t=>new Bone{name=t.name,parent=t.parent==null?null:t.parent.name,position=t.position}).ToArray(),
      material=new MaterialData{shader=material.shader.name,color=material.GetColor("_Color"),smoothness=material.GetFloat("_Glossiness"),
       metallic=material.GetFloat("_Metallic"),textures=material.GetTexturePropertyNames().Any(n=>material.GetTexture(n)!=null),
       property_block=source.HasPropertyBlock(),mode=material.GetFloat("_Mode")},
      runtime_component_present=source.GetComponent<UccNativeNormals>()!=null,
      profile=new Profile{unity=Application.unityVersion,color_space=QualitySettings.activeColorSpace.ToString(),
       skin_weights=QualitySettings.skinWeights.ToString(),renderer_quality=source.quality.ToString(),
       readable=mesh.isReadable,offscreen=source.updateWhenOffscreen,force_matrix_recalculation=source.forceMatrixRecalculationPerRender,
       max_influences=importer.maxBonesPerVertex,minimum_weight=importer.minBoneWeight,import_animation=importer.importAnimation,
       optimize_bones=importer.optimizeBones,bake_axis=importer.bakeAxisConversion,
       animation_clips=AssetDatabase.LoadAllAssetsAtPath("Assets/UCC/character.fbx").OfType<AnimationClip>().Count()}};
    }
   } finally {UnityEngine.Object.DestroyImmediate(baked);}
  }
 }
}
