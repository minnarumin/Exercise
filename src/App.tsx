import React, { FormEvent, useMemo, useState } from 'react';

type RecipeResponse = {
  recipeNo: number;
  startDevice: string;
  values: number[];
};

type PlcStatus = {
  connected: boolean;
};

const API_BASE = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:3001';

export function App() {
  const [plcHost, setPlcHost] = useState('192.168.3.39');
  const [plcPort, setPlcPort] = useState(5000);
  const [recipeNo, setRecipeNo] = useState(1);
  const [wordsPerRecipe, setWordsPerRecipe] = useState(10);
  const [payload, setPayload] = useState('100,200,300,400,500,600,700,800,900,1000');
  const [result, setResult] = useState<RecipeResponse | null>(null);
  const [status, setStatus] = useState<PlcStatus | null>(null);
  const [message, setMessage] = useState('');
  const [isLoading, setIsLoading] = useState(false);

  const parsedPayload = useMemo(
    () => payload.split(',').map((v: string) => Number(v.trim())).filter((v: number) => !Number.isNaN(v)),
    [payload],
  );

  const connect = async (e: FormEvent) => {
    e.preventDefault();
    setIsLoading(true);
    setMessage('');
    try {
      const res = await fetch(`${API_BASE}/api/plc/connect`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ host: plcHost, port: plcPort }),
      });
      if (!res.ok) throw new Error(await res.text());
      const data = (await res.json()) as PlcStatus;
      setStatus(data);
      setMessage('PLCに接続しました。');
    } catch (error) {
      setMessage(`接続に失敗しました: ${(error as Error).message}`);
    } finally {
      setIsLoading(false);
    }
  };

  const loadRecipe = async () => {
    setIsLoading(true);
    setMessage('');
    try {
      const res = await fetch(
        `${API_BASE}/api/recipes/${recipeNo}?wordsPerRecipe=${wordsPerRecipe}`,
      );
      if (!res.ok) throw new Error(await res.text());
      const data = (await res.json()) as RecipeResponse;
      setResult(data);
      setPayload(data.values.join(','));
      setMessage(`レシピ${recipeNo}を読み込みました。`);
    } catch (error) {
      setMessage(`読み込みに失敗しました: ${(error as Error).message}`);
    } finally {
      setIsLoading(false);
    }
  };

  const saveRecipe = async () => {
    setIsLoading(true);
    setMessage('');
    try {
      const res = await fetch(`${API_BASE}/api/recipes/${recipeNo}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ values: parsedPayload, wordsPerRecipe }),
      });
      if (!res.ok) throw new Error(await res.text());
      const data = (await res.json()) as RecipeResponse;
      setResult(data);
      setMessage(`レシピ${recipeNo}を保存しました。`);
    } catch (error) {
      setMessage(`保存に失敗しました: ${(error as Error).message}`);
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <main className="container">
      <h1>三菱PLC レシピ管理（ZR1〜ZR1000）</h1>
      <form className="card" onSubmit={connect}>
        <h2>PLC接続</h2>
        <label>
          IPアドレス
          <input value={plcHost} onChange={(e: React.ChangeEvent<HTMLInputElement>) => setPlcHost(e.target.value)} required />
        </label>
        <label>
          ポート
          <input
            type="number"
            value={plcPort}
            onChange={(e: React.ChangeEvent<HTMLInputElement>) => setPlcPort(Number(e.target.value))}
            min={1}
            max={65535}
          />
        </label>
        <button disabled={isLoading}>接続</button>
        <p>接続状態: {status?.connected ? 'Connected' : 'Disconnected'}</p>
      </form>

      <section className="card">
        <h2>レシピ読み書き</h2>
        <label>
          レシピ番号 (1-100)
          <input
            type="number"
            value={recipeNo}
            onChange={(e: React.ChangeEvent<HTMLInputElement>) => setRecipeNo(Number(e.target.value))}
            min={1}
            max={100}
          />
        </label>
        <label>
          1レシピのワード数
          <input
            type="number"
            value={wordsPerRecipe}
            onChange={(e: React.ChangeEvent<HTMLInputElement>) => setWordsPerRecipe(Number(e.target.value))}
            min={1}
            max={200}
          />
        </label>
        <label>
          レシピ値（カンマ区切り）
          <textarea value={payload} onChange={(e: React.ChangeEvent<HTMLTextAreaElement>) => setPayload(e.target.value)} rows={4} />
        </label>
        <div className="actions">
          <button onClick={loadRecipe} disabled={isLoading}>読み込み</button>
          <button onClick={saveRecipe} disabled={isLoading}>保存</button>
        </div>
        {message && <p>{message}</p>}
        {result && (
          <div className="result">
            <p>デバイス: {result.startDevice}</p>
            <p>値: {result.values.join(', ')}</p>
          </div>
        )}
      </section>
    </main>
  );
}
