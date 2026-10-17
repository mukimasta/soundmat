/** 把状态中心推来的变化（点号路径 → 新值）应用到状态树上，返回新的对象（不修改原对象）。 */
export type Tree = Record<string, unknown>;

export function applyChange(tree: Tree, path: string, value: unknown): Tree {
  const keys = path.split('.');
  const root: Tree = { ...tree };
  let node: Tree = root;
  for (let i = 0; i < keys.length - 1; i++) {
    const k = keys[i];
    const next = node[k];
    const copy: Tree = next && typeof next === 'object' && !Array.isArray(next) ? { ...(next as Tree) } : {};
    node[k] = copy;
    node = copy;
  }
  node[keys[keys.length - 1]] = value;
  return root;
}

export function applyChanges(tree: Tree, changes: [string, unknown][]): Tree {
  return changes.reduce((t, [p, v]) => applyChange(t, p, v), tree);
}

/** 按点号路径读取；不存在时返回 undefined。 */
export function getPath<T = unknown>(tree: Tree | undefined, path: string): T | undefined {
  let node: unknown = tree;
  for (const k of path.split('.')) {
    if (!node || typeof node !== 'object') return undefined;
    node = (node as Tree)[k];
  }
  return node as T | undefined;
}
