const fs = require('fs');
const path = require('path');
const src = fs.readFileSync(path.join(__dirname, '..', 'frontend', 'js', 'main.js'), 'utf8');

const used = new Set();
const callRe = /([A-Za-z_$][\w$]*)\s*\(/g;
let m;
while ((m = callRe.exec(src)) !== null) {
  used.add(m[1]);
}

const defined = new Set();
// function declarations
let fnRe = /function\s+([A-Za-z_$][\w$]*)/g;
while ((m = fnRe.exec(src)) !== null) defined.add(m[1]);
// const/let/var name = function or arrow
fnRe = /(?:const|let|var)\s+([A-Za-z_$][\w$]*)\s*=/g;
while ((m = fnRe.exec(src)) !== null) defined.add(m[1]);
// window.name =
fnRe = /window\.([A-Za-z_$][\w$]*)\s*=/g;
while ((m = fnRe.exec(src)) !== null) defined.add(m[1]);
// object method shorthand:  name(args) {
fnRe = /^\s*([A-Za-z_$][\w$]*)\s*\([^)]*\)\s*\{/gm;
while ((m = fnRe.exec(src)) !== null) defined.add(m[1]);
// class
fnRe = /class\s+([A-Za-z_$][\w$]*)/g;
while ((m = fnRe.exec(src)) !== null) defined.add(m[1]);

const keywords = new Set(['if','for','while','switch','catch','return','function','typeof','new','delete','void','do','else','case','default','in','of','throw','try','finally','let','const','var','async','await','yield','class','extends','super','this','import','export','from','with','enum','debugger']);

const candidates = [...used].filter(u =>
  !keywords.has(u) &&
  !defined.has(u) &&
  /^[a-z_$]/.test(u)
);

// Now check which of these are actually globals/builtins by checking if they exist on globalThis
const builtinsOnGlobal = new Set();
const builtinNames = ['Object','Array','String','Number','Boolean','Function','Symbol','RegExp','Date','Promise','Math','JSON','parseInt','parseFloat','isNaN','isFinite','encodeURIComponent','decodeURIComponent','encodeURI','decodeURI','escape','unescape','eval','console','window','document','location','navigator','history','localStorage','sessionStorage','fetch','WebSocket','Blob','FileReader','File','Node','AbortController','URL','URLSearchParams','Blob','FormData','Headers','Request','Response','AbortSignal','setInterval','setTimeout','clearInterval','clearTimeout','requestAnimationFrame','cancelAnimationFrame','structuredClone','atob','btoa','crypto','performance','navigator','screen','visualViewport','IntersectionObserver','ResizeObserver','MutationObserver','Event','CustomEvent','HTMLElement','Element','Text','Comment','DocumentFragment','getComputedStyle','scrollTo','scrollBy','alert','confirm','prompt','open','close','print','matchMedia','innerWidth','innerHeight','innerHeight','outerWidth','outerHeight','requestIdleCallback','cancelIdleCallback','queueMicrotask','setImmediate','globalThis','global','require','module','exports','process','Buffer','Set','Map','WeakMap','WeakSet','Proxy','Reflect','WeakRef','FinalizationRegistry','Atomics','SharedArrayBuffer','WebAssembly','TextEncoder','TextDecoder','ReadableStream','WritableStream','TransformStream','CompressionStream','DecompressionStream','Error','TypeError','RangeError','SyntaxError','ReferenceError','URIError','EvalError','AggregateError','DOMException','DOMParser','XMLHttpRequest','Image','Audio','Worker','SharedWorker','MessageChannel','MessagePort','BroadcastChannel','Cache','CacheStorage','ServiceWorker','ServiceWorkerContainer','ServiceWorkerRegistration','Notification','PushManager','PushSubscription','Geolocation','BatteryManager','MediaQueryList','Storage','StorageEvent','StorageManager','CustomEvent','EventTarget','Event','AbortController','AbortSignal','CloseEvent','ProgressEvent','HashChangeEvent','PopStateEvent','ErrorEvent','FocusEvent','KeyboardEvent','MouseEvent','PointerEvent','TouchEvent','WheelEvent','AnimationEvent','TransitionEvent','beforeinstallpromptevent','BeforeInstallPromptEvent','GamepadEvent','InputEvent','UIEvent','XMLHttpRequestProgressEvent','XMLHttpRequestUpload','IDBDatabase','IDBObjectStore','IDBIndex','IDBKeyRange','IDBTransaction','IDBCursor','IDBRequest','IDBOpenDBRequest','IDBFactory','IDBVersionChangeEvent','IDBValidKey','IDBNameRequiredError','IDBNotFoundError','IDBConstraintError','IDBReadOnlyError','IDBTransactionInactiveError','IDBObjectStoreUnknownError','IDBTransactionUnknownError','DOMException','DOMTokenList','CSSStyleDeclaration','CSSUnitValue','CSSPerspectiveValue','CSSRotateValue','CSSScaleValue','CSSSkewXValue','CSSSkewYValue','CSSSkewValue','CSSMatrixComponent','CSSUnparsedValue','CSSValue','CSSValueList','CSSUnitValue','CSSPrimitiveValue','CSS2Properties','CSSDeclaration','CSSStyleRule','CSSMediaRule','CSSImportRule','CSSNamespaceRule','CSSCounterStyleRule','CSSFontFaceRule','CSSPageRule','CSSSupportsRule','CSSTransition','CSSTransitionRule','HTMLElement','HTMLInputElement','HTMLSelectElement','HTMLTextAreaElement','HTMLButtonElement','HTMLAnchorElement','HTMLImageElement','HTMLVideoElement','HTMLAudioElement','HTMLCanvasElement','HTMLIFrameElement','HTMLObjectElement','HTMLEmbedElement','HTMLSourceElement','HTMLTrackElement','HTMLMapElement','HTMLParamElement','HTMLTableElement','HTMLTableRowElement','HTMLTableCellElement','HTMLFormElement','HTMLFieldSetElement','HTMLLabelElement','HTMLLegendElement','HTMLOptGroupElement','HTMLOptionElement','HTMLDataListElement','HTMLProgressElement','HTMLMeterElement','HTMLUnknownElement','HTMLTemplateElement','HTMLSlotElement','HTMLShadowElement','SVGElement','SVGGraphicsElement','SVGSVGElement','HTMLMediaElement','HTMLVideoElement','HTMLAudioElement','AudioTrack','VideoTrack','TextTrack','TextTrackCue','TextTrackList','TimeRanges','AudioContext','AudioNode','AudioParam','AudioBuffer','AudioBufferSourceNode','AudioDestinationNode','AudioListener','AudioWorklet','AudioWorkletGlobalScope','AudioWorkletNode','MediaStream','MediaStreamTrack','MediaRecorder','MediaSource','MediaElementAudioSourceNode','MediaStreamAudioSourceNode','MediaStreamAudioDestinationNode','MediaStreamAudioDestinationNode','MediaStreamEvent','MediaStreamProcessor','MediaElementSourceNode','MediaElementAudioSourceNode','MediaElementAudioSourceNode','MediaElementAudioSourceNode','MediaElementAudioSourceNode','MediaElementAudioSourceNode','MediaElementAudioSourceNode'];

const result = candidates.filter(c => !builtinNames.includes(c));
console.log('Referenced but not locally defined (need to verify against globals):');
result.sort().forEach(c => console.log('  ' + c));
