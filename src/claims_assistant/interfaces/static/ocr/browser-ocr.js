/* Browser-only OCR. All worker, core, and language downloads stay on this origin. */
(() => {
  const assets = new URL('/assets/ocr/6.0.1/', window.location.href).href;
  let library;
  let running = false;

  function loadLibrary() {
    if (window.Tesseract) return Promise.resolve(window.Tesseract);
    if (!library) {
      library = new Promise((resolve, reject) => {
        const script = document.createElement('script');
        script.src = assets + 'tesseract.min.js';
        script.onload = () => resolve(window.Tesseract);
        script.onerror = () => {
          script.remove();
          library = null;
          reject(new Error('The browser OCR files could not load. Check your connection and retry.'));
        };
        document.head.append(script);
      });
    }
    return library;
  }

  async function scan(file, progress = () => {}) {
    if (running) throw new Error('A receipt scan is already running.');
    running = true;
    let worker;
    let bitmap;
    let canvas;
    let expired = false;
    let timer;
    const work = async () => {
      if (file.size > 5 * 1024 * 1024) throw new Error('Maximum file size: 5 MiB.');
      const header = new Uint8Array(await file.slice(0, 8).arrayBuffer());
      const png = [137, 80, 78, 71, 13, 10, 26, 10].every((byte, i) => header[i] === byte);
      const jpeg = header[0] === 255 && header[1] === 216 && header[2] === 255;
      if (!png && !jpeg) throw new Error('Choose a valid PNG or JPEG receipt image.');
      if (png) {
        const bytes = new Uint8Array(await file.arrayBuffer());
        const view = new DataView(bytes.buffer);
        for (let offset = 8; offset + 12 <= bytes.length;) {
          const length = view.getUint32(offset);
          const type = String.fromCharCode(...bytes.slice(offset + 4, offset + 8));
          if (type === 'acTL') throw new Error('Use a single-frame PNG or JPEG receipt.');
          if (type === 'IDAT' || length > bytes.length - offset - 12) break;
          offset += length + 12;
        }
      }
      progress('Preparing receipt image...');
      try {
        bitmap = await createImageBitmap(file);
      } catch {
        throw new Error('The image could not be decoded. Choose a clear PNG or JPEG.');
      }
      if (expired) return '';
      if (bitmap.width * bitmap.height > 20000000) {
        throw new Error('Receipt image exceeds 20 million pixels.');
      }
      const scale = Math.min(1, 2400 / Math.max(bitmap.width, bitmap.height));
      canvas = document.createElement('canvas');
      canvas.width = Math.max(1, Math.round(bitmap.width * scale));
      canvas.height = Math.max(1, Math.round(bitmap.height * scale));
      const context = canvas.getContext('2d');
      context.fillStyle = 'white';
      context.fillRect(0, 0, canvas.width, canvas.height);
      context.drawImage(bitmap, 0, 0, canvas.width, canvas.height);
      bitmap.close();
      bitmap = null;
      progress('Loading browser OCR. The first scan downloads its files...');
      const engine = await loadLibrary();
      if (expired) return '';
      const loading = engine.createWorker('eng', 1, {
        workerPath: assets + 'worker.min.js',
        corePath: assets,
        langPath: assets,
        workerBlobURL: false,
        cacheMethod: 'none',
        errorHandler: () => {},
        logger: ({ status, progress: fraction }) => {
          if (!expired && status === 'recognizing text') {
            const percent = Math.round(Math.max(0, Math.min(1, fraction || 0)) * 100);
            progress(`Reading receipt in your browser: ${percent}%`);
          }
        },
      });
      loading.then((created) => {
        if (expired) created.terminate();
        else worker = created;
      }).catch(() => {});
      worker = await loading;
      if (expired) { await worker.terminate(); return ''; }
      await worker.setParameters({ tessedit_pageseg_mode: '6', preserve_interword_spaces: '1' });
      const result = await worker.recognize(canvas);
      const text = (result.data.text || '').trim();
      if (!text || !/[A-Za-z0-9]/.test(text)) {
        throw new Error('No readable receipt text found. Try a clearer image.');
      }
      if (text.length > 20000) throw new Error('Scanned text exceeds 20,000 characters.');
      return text;
    };
    try {
      const deadline = new Promise((_, reject) => {
        timer = setTimeout(() => {
          expired = true;
          reject(new Error('Browser OCR timed out. Try a smaller, clearer image.'));
        }, 120000);
      });
      return await Promise.race([work(), deadline]);
    } catch (error) {
      // Do not expose arbitrary worker errors or OCR content as error messages.
      const safe = /^(Maximum file size|Choose a valid|Use a single-frame|The image could not be decoded|Receipt image exceeds|No readable receipt text|Scanned text exceeds|Browser OCR timed out|The browser OCR files)/;
      if (error instanceof Error && safe.test(error.message)) throw error;
      throw new Error('Browser OCR could not read this image. Check the OCR asset requests and retry with a clear receipt.');
    } finally {
      expired = true;
      clearTimeout(timer);
      if (worker) await worker.terminate();
      if (bitmap) bitmap.close();
      if (canvas) canvas.width = canvas.height = 0;
      running = false;
    }
  }

  window.ClaimsBrowserOCR = { scan };
})();
