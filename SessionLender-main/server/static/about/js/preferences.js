export function readPreference(key, fallback) {
  try {
    return localStorage.getItem(key) || fallback;
  } catch (_) {
    return fallback;
  }
}
export function savePreference(key, value) {
  try {
    localStorage.setItem(key, value);
  } catch (_) {
    /* Private mode still works. */
  }
}
