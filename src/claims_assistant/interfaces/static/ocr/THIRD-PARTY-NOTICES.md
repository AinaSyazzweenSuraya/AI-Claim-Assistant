# Browser OCR dependencies

These assets are self-hosted so receipt images need not leave the browser for OCR.

- Tesseract.js 6.0.1, https://github.com/naptha/tesseract.js: Apache-2.0.
  See `6.0.1/TESSERACT-JS-LICENSE.txt` and the two bundled `.LICENSE.txt` notices.
- tesseract.js-core 6.0.0, https://github.com/naptha/tesseract.js-core: Apache-2.0.
  See `6.0.1/TESSERACT-CORE-LICENSE.txt`. Both LSTM-only WebAssembly builds are included.
- English package `@tesseract.js-data/eng` 1.0.0 from https://github.com/naptha/tessdata:
  package metadata declares MIT; its original metadata and attribution are preserved in
  `6.0.1/ENG-PACKAGE.json`. Underlying Tesseract language data originates from the Apache-2.0
  Tesseract project.

Pinned package integrity values and per-file hashes are in `6.0.1/manifest.json`.
Reproduce the files with `scripts/vendor_browser_ocr.py` without executing package code.
The app's `browser-ocr.js` is the integration helper, separate from upstream assets.
