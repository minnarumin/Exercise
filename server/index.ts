import cors from 'cors';
import express from 'express';
import mcprotocol from 'mcprotocol';

type PlcConnectOptions = { host: string; port: number };

const MAX_ZR = 1000;
const DEFAULT_WORDS_PER_RECIPE = 10;
const app = express();
app.use(cors());
app.use(express.json());

const plc = new mcprotocol();
let isConnected = false;

plc.setTranslationCB((tag: string) => tag);

function recipeStartAddress(recipeNo: number, wordsPerRecipe: number): number {
  return (recipeNo - 1) * wordsPerRecipe + 1;
}

function validateRecipeNo(recipeNo: number): void {
  if (Number.isNaN(recipeNo) || recipeNo < 1 || recipeNo > 100) {
    throw new Error('recipeNoは1-100で指定してください。ZR1-1000を100レシピに分割します。');
  }
}

function validateWordsPerRecipe(wordsPerRecipe: number): void {
  if (Number.isNaN(wordsPerRecipe) || wordsPerRecipe < 1 || wordsPerRecipe > 200) {
    throw new Error('wordsPerRecipeは1-200で指定してください。');
  }
}

function ensureRange(start: number, length: number): void {
  const end = start + length - 1;
  if (start < 1 || end > MAX_ZR) {
    throw new Error(`ZR範囲外です: ZR${start}〜ZR${end}。許容範囲はZR1〜ZR${MAX_ZR}`);
  }
}

function connectToPlc(options: PlcConnectOptions): Promise<void> {
  return new Promise((resolve, reject) => {
    plc.initiateConnection({ host: options.host, port: options.port }, (err: Error | undefined) => {
      if (err) {
        reject(err);
        return;
      }
      isConnected = true;
      resolve();
    });
  });
}

function readWords(startDevice: string, length: number): Promise<number[]> {
  return new Promise((resolve, reject) => {
    plc.readItems(`${startDevice},${length}`, (err: Error | undefined, values: unknown) => {
      if (err) {
        reject(err);
        return;
      }
      if (!Array.isArray(values)) {
        reject(new Error('PLCからの読込データ形式が不正です。'));
        return;
      }
      resolve(values.map((v) => Number(v)));
    });
  });
}

function writeWords(startDevice: string, values: number[]): Promise<void> {
  return new Promise((resolve, reject) => {
    plc.writeItems(`${startDevice},${values.length}`, values, (err: Error | undefined) => {
      if (err) {
        reject(err);
        return;
      }
      resolve();
    });
  });
}

app.post('/api/plc/connect', async (req, res) => {
  try {
    const host = String(req.body.host ?? '');
    const port = Number(req.body.port ?? 5000);
    await connectToPlc({ host, port });
    res.json({ connected: true });
  } catch (error) {
    res.status(500).send((error as Error).message);
  }
});

app.get('/api/recipes/:recipeNo', async (req, res) => {
  try {
    if (!isConnected) throw new Error('PLC未接続です。先に接続してください。');

    const recipeNo = Number(req.params.recipeNo);
    const wordsPerRecipe = Number(req.query.wordsPerRecipe ?? DEFAULT_WORDS_PER_RECIPE);
    validateRecipeNo(recipeNo);
    validateWordsPerRecipe(wordsPerRecipe);

    const start = recipeStartAddress(recipeNo, wordsPerRecipe);
    ensureRange(start, wordsPerRecipe);
    const startDevice = `ZR${start}`;

    const values = await readWords(startDevice, wordsPerRecipe);
    res.json({ recipeNo, startDevice, values });
  } catch (error) {
    res.status(400).send((error as Error).message);
  }
});

app.put('/api/recipes/:recipeNo', async (req, res) => {
  try {
    if (!isConnected) throw new Error('PLC未接続です。先に接続してください。');

    const recipeNo = Number(req.params.recipeNo);
    const wordsPerRecipe = Number(req.body.wordsPerRecipe ?? DEFAULT_WORDS_PER_RECIPE);
    const values = (req.body.values as number[]).map((v) => Number(v));

    validateRecipeNo(recipeNo);
    validateWordsPerRecipe(wordsPerRecipe);
    if (values.length !== wordsPerRecipe) {
      throw new Error(`valuesの件数(${values.length})とwordsPerRecipe(${wordsPerRecipe})を一致させてください。`);
    }

    const start = recipeStartAddress(recipeNo, wordsPerRecipe);
    ensureRange(start, wordsPerRecipe);
    const startDevice = `ZR${start}`;

    await writeWords(startDevice, values);
    res.json({ recipeNo, startDevice, values });
  } catch (error) {
    res.status(400).send((error as Error).message);
  }
});

const port = Number(process.env.PORT ?? 3001);
app.listen(port, () => {
  console.log(`PLC API server listening on port ${port}`);
});
