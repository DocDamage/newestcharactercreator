using System;
using System.IO;
using System.Linq;
using UnityEngine;
using UnityEditor;
using UnityEditor.SceneManagement;

namespace Ucc.UnityAdapter.Editor {
 public static class UccUnityExportJobs {
  [Serializable] sealed class Recipe {
   public int schema_version;public string policy,request_sha256,master_sha256,weights_sha256;
   public string fbx_sha256,source_reference_sha256,native_mesh_sha256,topology_sha256;
   public Color color_srgb;public float roughness;
  }
  static string Root=>Directory.GetParent(Application.dataPath).FullName;
  static void Bound(string file,string digest,int maximum) {
   var info=new FileInfo(file);
   if(digest==null||digest.Length!=64||!info.Exists||info.Length<1||info.Length>maximum||
      (info.Attributes&FileAttributes.ReparsePoint)!=0||UccNativeMeshIdentity.Hash(File.ReadAllBytes(file))!=digest)
    throw new InvalidDataException("Unity job input hash differs: "+Path.GetFileName(file));
  }
  static Recipe ReadRecipe() {
   var path=Path.Combine(Root,"engine_recipe.json");var file=new FileInfo(path);
   if(!file.Exists||file.Length<1||file.Length>65536||(file.Attributes&FileAttributes.ReparsePoint)!=0)
    throw new InvalidDataException("Bound Unity engine recipe missing or redirected");
   var recipe=JsonUtility.FromJson<Recipe>(File.ReadAllText(path));
   if(recipe==null||recipe.schema_version!=1||recipe.policy!="UCC_UNITY_EDITOR_JOB_V1"||Application.unityVersion!="6000.4.5f1")
    throw new InvalidDataException("Unsupported Unity engine recipe/version");
   Bound(Path.Combine(Root,"request.json"),recipe.request_sha256,256*1024);
   Bound(Path.Combine(Application.dataPath,"UCC/character.fbx"),recipe.fbx_sha256,512*1024*1024);
   Bound(Path.Combine(Application.dataPath,"UCC/source_weights.json"),recipe.weights_sha256,8*1024*1024);
   Bound(Path.Combine(Application.dataPath,"UCC/source_reference.json"),recipe.source_reference_sha256,64*1024*1024);
   return recipe;
  }
  static GameObject SavedRoot() {
   var scene=EditorSceneManager.OpenScene("Assets/UCC/Character.unity",OpenSceneMode.Single);
   var roots=scene.GetRootGameObjects();
   if(roots.Length!=1)throw new InvalidDataException("Saved character scene must have exactly one root");return roots[0];
  }
  static void WriteObservation(GameObject root,Recipe recipe,string mode,string filename) {
   var path=Path.Combine(Root,filename);
   if(File.Exists(path))throw new IOException("Refuse replacing Unity observation");
   var observation=UccUnityObservation.Read(root,recipe.request_sha256,recipe.master_sha256,mode);
   File.WriteAllText(path,JsonUtility.ToJson(observation));
  }
  public static void Stage() {try {
   var recipe=ReadRecipe();
   if(!String.IsNullOrEmpty(recipe.native_mesh_sha256)||!String.IsNullOrEmpty(recipe.topology_sha256))
    throw new InvalidDataException("Initial import cannot claim a preverified native mesh/topology");
   var result=UccUnityImport.Stage(recipe.weights_sha256,recipe.master_sha256,recipe.request_sha256,recipe.color_srgb,recipe.roughness);
   WriteObservation(result.Root,recipe,"stage","native-stage.json");
   Debug.Log("UCC_UNITY_SOURCE_IMPORT_STAGED_HOST_PARITY_REQUIRED");EditorApplication.Exit(0);
  }catch(Exception error){Debug.LogException(error);EditorApplication.Exit(2);}}
  public static void Attach() {try {
   var recipe=ReadRecipe();var root=SavedRoot();
   UccUnityImport.AttachValidatedTopology(root,recipe.topology_sha256,recipe.native_mesh_sha256);
   WriteObservation(root,recipe,"stage","native-attached.json");
   Debug.Log("UCC_UNITY_SOURCE_BOUND_ADAPTER_SAVED_FRESH_REOPEN_REQUIRED");EditorApplication.Exit(0);
  }catch(Exception error){Debug.LogException(error);EditorApplication.Exit(2);}}
  public static void Reopen() {try {
   var recipe=ReadRecipe();var root=SavedRoot();var skin=root.GetComponentsInChildren<SkinnedMeshRenderer>(true).Single();
   var component=skin.GetComponent<UccNativeNormals>();
   if(component==null||UccNativeMeshIdentity.Compute(skin)!=recipe.native_mesh_sha256)
    throw new InvalidDataException("Saved native adapter/mesh differs");
   var fields=new SerializedObject(component);
   var data=(TextAsset)fields.FindProperty("sourceData").objectReferenceValue;
   var digest=fields.FindProperty("sourceDataSha256").stringValue;
   var compute=(ComputeShader)fields.FindProperty("normalShader").objectReferenceValue;
   var warmup=(Shader)fields.FindProperty("warmupShader").objectReferenceValue;
   if(digest!=recipe.topology_sha256||AssetDatabase.GetAssetPath(data)!="Assets/UCC/source_quads.json"||
      compute==null||AssetDatabase.GetAssetPath(compute)!="Assets/UCC/UccQuadNormals.compute"||
      warmup==null||AssetDatabase.GetAssetPath(warmup)!="Assets/UCC/UccNativeSkinWarmup.shader")
    throw new InvalidDataException("Saved source topology or shader references differ");
   UccQuadSourceData.Read(data,digest,skin);
   WriteObservation(root,recipe,"reopen","native-reopen.json");
   Debug.Log("UCC_UNITY_SAVED_NATIVE_OBSERVATION_READ_WITHOUT_REPAIR_RUNTIME_NOT_VERIFIED");EditorApplication.Exit(0);
  }catch(Exception error){Debug.LogException(error);EditorApplication.Exit(2);}}
 }
}
