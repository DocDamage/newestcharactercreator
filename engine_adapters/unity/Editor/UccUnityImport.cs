using System;
using System.IO;
using System.Linq;
using UnityEngine;
using UnityEditor;
using UnityEditor.SceneManagement;

namespace Ucc.UnityAdapter.Editor {
 public static class UccUnityImport {
  public sealed class StagedCharacter {
   public GameObject Root; public SkinnedMeshRenderer Renderer; public int[] NativeSource;
   public string NativeMeshSha256;
  }
  static bool Finite(float v){return !float.IsNaN(v)&&!float.IsInfinity(v);}
  public static StagedCharacter Stage(string weightsSha,string masterSha,string requestSha,Color srgb,float roughness) {
   if(Application.unityVersion!="6000.4.5f1")throw new InvalidDataException("Unity editor differs from the admitted version");
   if(!Finite(roughness)||roughness<0||roughness>1||!Finite(srgb.r)||!Finite(srgb.g)||!Finite(srgb.b)||
      srgb.r<0||srgb.r>1||srgb.g<0||srgb.g>1||srgb.b<0||srgb.b>1||srgb.a!=1)
    throw new InvalidDataException("A finite opaque reviewed skin material is required");
   foreach(string name in new[]{"Character.prefab","Character.unity","CharacterSkin.asset","CharacterSkin.mat"})
    if(File.Exists("Assets/UCC/"+name)||AssetDatabase.LoadMainAssetAtPath("Assets/UCC/"+name)!=null)
     throw new InvalidDataException("Refuse replacing an existing character export");
   var importer=AssetImporter.GetAtPath("Assets/UCC/character.fbx") as ModelImporter;
   if(importer==null)throw new InvalidDataException("Actual staged FBX importer missing");
   importer.isReadable=true;importer.importAnimation=false;importer.importBlendShapes=true;
   importer.meshCompression=ModelImporterMeshCompression.Off;importer.weldVertices=false;
   importer.importNormals=ModelImporterNormals.Import;importer.importBlendShapeNormals=ModelImporterNormals.Import;
   // Unity clamps the raw-FBX threshold to .001. The explicit native mesh
   // conversion below restores and independently checks every positive source influence.
   importer.skinWeights=ModelImporterSkinWeights.Custom;importer.maxBonesPerVertex=8;importer.minBoneWeight=.001f;
   importer.optimizeBones=false;importer.optimizeGameObjects=false;importer.preserveHierarchy=true;importer.bakeAxisConversion=true;
   importer.globalScale=1;importer.useFileScale=true;importer.animationType=ModelImporterAnimationType.Generic;
   importer.SaveAndReimport();
   if(AssetDatabase.LoadAllAssetsAtPath("Assets/UCC/character.fbx").OfType<AnimationClip>().Any())
    throw new InvalidDataException("This static export must not contain animation clips");
   var source=AssetDatabase.LoadAssetAtPath<GameObject>("Assets/UCC/character.fbx");
   if(source==null)throw new InvalidDataException("Actual imported FBX hierarchy missing");
   EditorSceneManager.NewScene(NewSceneSetup.EmptyScene,NewSceneMode.Single);
   var root=(GameObject)PrefabUtility.InstantiatePrefab(source);
   var renderers=root.GetComponentsInChildren<SkinnedMeshRenderer>(true);
   if(renderers.Length!=1)throw new InvalidDataException("Expected exactly one admitted native skin");
   root.transform.rotation=Quaternion.AngleAxis(180,Vector3.up)*root.transform.rotation;
   var renderer=renderers[0];
   var mapping=UccSourceWeights.Apply(renderer,Path.Combine(Application.dataPath,"UCC/source_weights.json"),
                                    weightsSha,masterSha,requestSha,"Assets/UCC/CharacterSkin.asset");
   var shader=Shader.Find("Standard");if(shader==null)throw new InvalidDataException("Built-in Standard shader missing");
   var material=new Material(shader){name="UCC_Reviewed_Skin"};
   material.SetColor("_Color",srgb.linear);material.SetFloat("_Glossiness",1-roughness);material.SetFloat("_Metallic",0);
   AssetDatabase.CreateAsset(material,"Assets/UCC/CharacterSkin.mat");renderer.sharedMaterials=new[]{material};
   renderer.updateWhenOffscreen=true;renderer.quality=SkinQuality.Auto;
   PlayerSettings.colorSpace=ColorSpace.Linear;
   var quality=new SerializedObject(AssetDatabase.LoadAllAssetsAtPath("ProjectSettings/QualitySettings.asset")[0]);
   var levels=quality.FindProperty("m_QualitySettings");
   if(levels==null||!levels.isArray||levels.arraySize==0)throw new InvalidDataException("Quality profiles missing");
   for(int i=0;i<levels.arraySize;i++) {
    var property=levels.GetArrayElementAtIndex(i).FindPropertyRelative("skinWeights");
    if(property==null)throw new InvalidDataException("Native unlimited skin profile missing");property.intValue=255;
   }
   quality.ApplyModifiedPropertiesWithoutUndo();QualitySettings.skinWeights=SkinWeights.Unlimited;
   Save(root);
   return new StagedCharacter{Root=root,Renderer=renderer,NativeSource=mapping,NativeMeshSha256=UccNativeMeshIdentity.Compute(renderer)};
  }
  // Stage-only persistence; saved-scene verification must never call this method.
  public static void AttachValidatedTopology(GameObject root,string topologySha,string nativeMeshSha) {
   if(Application.isPlaying||root==null||root.scene.path!="Assets/UCC/Character.unity")
    throw new InvalidOperationException("Topology attachment requires the owned staged character scene");
   var skins=root.GetComponentsInChildren<SkinnedMeshRenderer>(true);
   if(skins.Length!=1||skins[0].GetComponent<UccNativeNormals>()!=null)
    throw new InvalidDataException("Refuse replacing or ambiguously attaching a native normal adapter");
   var source=skins[0];
   if(UccNativeMeshIdentity.Compute(source)!=nativeMeshSha)throw new InvalidDataException("Staged native mesh changed before topology attachment");
   var data=AssetDatabase.LoadAssetAtPath<TextAsset>("Assets/UCC/source_quads.json");
   UccQuadSourceData.Read(data,topologySha,source);
   var compute=AssetDatabase.LoadAssetAtPath<ComputeShader>("Assets/UCC/UccQuadNormals.compute");
   var warmup=AssetDatabase.LoadAssetAtPath<Shader>("Assets/UCC/UccNativeSkinWarmup.shader");
   if(compute==null||warmup==null||warmup.name!="Hidden/UCC/NativeSkinWarmup")
    throw new InvalidDataException("Actual staged native normal shaders are missing");
   var component=source.gameObject.AddComponent<UccNativeNormals>();
   try {component.ConfigureForExport(data,topologySha,compute,warmup);Save(root);}
   catch {UnityEngine.Object.DestroyImmediate(component);throw;}
  }
  // Stage-only persistence; saved-scene verification must never call this method.
  public static void Save(GameObject root) {
   if(PrefabUtility.SaveAsPrefabAsset(root,"Assets/UCC/Character.prefab")==null)
    throw new IOException("Could not persist the staged character prefab");
   if(!EditorSceneManager.SaveScene(root.scene,"Assets/UCC/Character.unity"))throw new IOException("Could not persist the staged character scene");
   AssetDatabase.SaveAssets();
  }
 }
}
