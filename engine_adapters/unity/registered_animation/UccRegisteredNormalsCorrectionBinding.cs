using System;
using System.IO;
using UnityEngine;
using UnityEngine.Rendering;

namespace Ucc.UnityAdapter {
    /// <summary>Portable asset references for the explicitly selected registered correction.</summary>
    public sealed class UccRegisteredNormalsCorrectionBinding : ScriptableObject, IUccNativePositionCorrectionBinding {
        [SerializeField] ComputeShader correctionShader;
        [SerializeField] UccCorrectionTopologyAsset[] topologyAssets;

#if UNITY_EDITOR
        public void ConfigureForExport(ComputeShader shader, UccCorrectionTopologyAsset[] resources) {
            if (Application.isPlaying) throw new InvalidOperationException("Do not replace a running correction binding");
            if (shader == null || resources == null || resources.Length != 6)
                throw new InvalidDataException("Registered correction needs its shader and six exact topology assets");
            correctionShader = shader;
            topologyAssets = (UccCorrectionTopologyAsset[])resources.Clone();
        }
#endif

        public IUccNativePositionCorrection CreateCorrection(int[] nativeToSource) {
            return new Session(new UccRegisteredCorrection(correctionShader, nativeToSource, topologyAssets));
        }

        sealed class Session : IUccNativePositionCorrection {
            readonly UccRegisteredCorrection correction;

            public Session(UccRegisteredCorrection correction) { this.correction = correction; }

            public void Record(CommandBuffer commands, GraphicsBuffer nativeSkin, GraphicsBuffer ownedDraw) {
                correction.Record(commands, nativeSkin, ownedDraw);
            }

            public void Dispose() => correction.Dispose();
        }
    }
}
