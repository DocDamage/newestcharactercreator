using System;
using System.IO;
using System.Linq;
using UnityEngine;
using UnityEditor;
using UnityEditor.SceneManagement;

namespace Ucc.UnityAdapter.Editor {
 [InitializeOnLoad] public static class UccUnityRuntimeJob {
  static string Root=>Directory.GetParent(Application.dataPath).FullName;
  [Serializable] sealed class Inputs {public string plan_sha256,request_sha256,native_mesh_sha256,topology_sha256;}
  static UccUnityRuntimeJob(){EditorApplication.update+=Check;EditorApplication.playModeStateChanged+=State;}
  public static void Run(){try {
   foreach(string name in new[]{"runtime-done.txt","runtime-observation.json","runtime-native.bin","runtime-job-active.txt"})
    if(File.Exists(Path.Combine(Root,name)))throw new IOException("Refuse replacing existing runtime observation");
   var file=new FileInfo(Path.Combine(Root,"runtime-inputs.json"));
   if(!file.Exists||file.Length>65536)throw new InvalidDataException("Bound runtime inputs missing");
   var input=JsonUtility.FromJson<Inputs>(File.ReadAllText(file.FullName));
   var plan=File.ReadAllBytes(Path.Combine(Root,"runtime-plan.json"));
   if(plan.Length>2*1024*1024||UccNativeMeshIdentity.Hash(plan)!=input.plan_sha256||UccNativeMeshIdentity.Hash(File.ReadAllBytes(Path.Combine(Root,"request.json")))!=input.request_sha256)
    throw new InvalidDataException("Runtime plan/request hash differs");
   var data=JsonUtility.FromJson<UccUnityRuntimeObserver.Plan>(System.Text.Encoding.UTF8.GetString(plan));
   if(data.request_sha256!=input.request_sha256||data.native_mesh_sha256!=input.native_mesh_sha256||data.topology_sha256!=input.topology_sha256)
    throw new InvalidDataException("Runtime plan bindings differ");
   var scene=EditorSceneManager.OpenScene("Assets/UCC/Character.unity",OpenSceneMode.Single);var roots=scene.GetRootGameObjects();
   if(roots.Length!=1)throw new InvalidDataException("Saved runtime scene root differs");
   var skin=roots[0].GetComponentsInChildren<SkinnedMeshRenderer>(true).Single();var component=skin.GetComponent<UccNativeNormals>();
   if(component==null||UccNativeMeshIdentity.Compute(skin)!=input.native_mesh_sha256)throw new InvalidDataException("Saved runtime native identity differs");
   var fields=new SerializedObject(component);
   if(fields.FindProperty("sourceDataSha256").stringValue!=input.topology_sha256)throw new InvalidDataException("Saved runtime topology binding differs");
   File.WriteAllText(Path.Combine(Root,"runtime-job-active.txt"),input.plan_sha256);EditorApplication.isPlaying=true;
  }catch(Exception error){Debug.LogException(error);EditorApplication.Exit(2);}}
  static void State(PlayModeStateChange state){
   if(state!=PlayModeStateChange.EnteredPlayMode||!File.Exists(Path.Combine(Root,"runtime-job-active.txt")))return;
   try {UnityEngine.SceneManagement.SceneManager.GetActiveScene().GetRootGameObjects().Single().AddComponent<UccUnityRuntimeObserver>();}
   catch(Exception error){Debug.LogException(error);EditorApplication.Exit(2);}
  }
  static void Check(){var path=Path.Combine(Root,"runtime-done.txt");if(File.Exists(path))EditorApplication.Exit(Int32.Parse(File.ReadAllText(path)));}
 }
}
