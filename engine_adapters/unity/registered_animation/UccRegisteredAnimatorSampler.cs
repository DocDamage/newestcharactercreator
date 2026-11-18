using System;
using System.IO;
using UnityEngine;

namespace Ucc.UnityAdapter {
    // The verifier samples the same live Animator that has already looped normally.
    // Expected source vectors never enter Unity's process.
    public static class UccRegisteredAnimatorSampler {
        public const int Samples = 300;
        public const int FramesPerSecond = 30;
        public const float DurationSeconds = 10f;

        public static void VisitFrames(Animator animator, int stateHash, Action<int> observe) {
            if (!Application.isPlaying || animator == null || !animator.isInitialized || observe == null)
                throw new InvalidDataException("The registered sampler requires an actual live Animator");
            for (int sample = 0; sample < Samples; sample++) {
                float phase = sample / (float)Samples;
                animator.Play(stateHash, 0, phase);
                animator.Update(0f);
                var state = animator.GetCurrentAnimatorStateInfo(0);
                if (state.fullPathHash != stateHash || Mathf.Abs(state.normalizedTime - phase) > .00001f)
                    throw new InvalidDataException("Native Animator did not sample the registered fixed clock");
                observe(sample);
            }
        }

        public static bool Finite(float value) => !float.IsNaN(value) && !float.IsInfinity(value);

        public static float[] RowMajor(Matrix4x4 matrix) {
            var values = new float[16];
            for (int row = 0; row < 4; row++)
                for (int column = 0; column < 4; column++) {
                    float value = matrix[row, column];
                    if (!Finite(value)) throw new InvalidDataException("Nonfinite native world bone matrix");
                    values[row * 4 + column] = value;
                }
            return values;
        }
    }
}
