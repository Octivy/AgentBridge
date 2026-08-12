using System;
using System.Collections.Concurrent;
using System.Threading.Tasks;
using Autodesk.AutoCAD.ApplicationServices;

namespace AgentBridge.Core
{
    public static class MainThreadDispatcher
    {
        private static readonly ConcurrentQueue<Action> Queue = new ConcurrentQueue<Action>();
        private static bool _initialized;

        public static void Initialize()
        {
            if (_initialized)
            {
                return;
            }

            Application.Idle += ProcessQueue;
            _initialized = true;
            Logger.Info("MainThreadDispatcher initialized.");
        }

        public static void Shutdown()
        {
            if (!_initialized)
            {
                return;
            }

            Application.Idle -= ProcessQueue;
            _initialized = false;
        }

        public static void Enqueue(Action action)
        {
            if (action == null)
            {
                return;
            }

            Queue.Enqueue(action);
        }

        public static Task InvokeAsync(Action action)
        {
            if (action == null)
            {
                throw new ArgumentNullException(nameof(action));
            }

            TaskCompletionSource<bool> completionSource = new TaskCompletionSource<bool>();
            Enqueue(() =>
            {
                try
                {
                    action();
                    completionSource.TrySetResult(true);
                }
                catch (Exception ex)
                {
                    completionSource.TrySetException(ex);
                }
            });

            return completionSource.Task;
        }

        public static Task<T> InvokeAsync<T>(Func<T> func)
        {
            if (func == null)
            {
                throw new ArgumentNullException(nameof(func));
            }

            TaskCompletionSource<T> completionSource = new TaskCompletionSource<T>();
            Enqueue(() =>
            {
                try
                {
                    completionSource.TrySetResult(func());
                }
                catch (Exception ex)
                {
                    completionSource.TrySetException(ex);
                }
            });

            return completionSource.Task;
        }

        private static void ProcessQueue(object sender, EventArgs e)
        {
            int processed = 0;
            while (processed < 5 && Queue.TryDequeue(out Action action))
            {
                try
                {
                    action();
                }
                catch (Exception ex)
                {
                    Logger.Error("Main thread task failed: " + ex);
                }

                processed++;
            }
        }
    }
}