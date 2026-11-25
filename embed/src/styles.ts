// All widget CSS. It lives only inside the Shadow DOM, so the website can't break it and it can't
// touch the website. Colours come from CSS variables set on the host element (see element.ts).
export const CSS = `
:host{all:initial!important}
*,*::before,*::after{box-sizing:border-box}
.cc{font-family:system-ui,-apple-system,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;font-size:15px;line-height:1.45;color:var(--cc-text);-webkit-font-smoothing:antialiased}
button{font:inherit;color:inherit;background:none;border:0;margin:0;padding:0;cursor:pointer}
a{color:var(--cc-link)}
:focus{outline:none}
:focus-visible{outline:3px solid var(--cc-focus);outline-offset:2px}
.cc-sr{position:absolute!important;width:1px;height:1px;overflow:hidden;clip:rect(0 0 0 0);white-space:nowrap}

/* Launcher */
.cc-launcher{position:fixed;z-index:var(--cc-z);bottom:calc(24px + env(safe-area-inset-bottom,0px));width:60px;height:60px;border-radius:50%;display:flex;align-items:center;justify-content:center;background:var(--cc-primary);color:var(--cc-on-primary);box-shadow:0 6px 20px rgba(0,0,0,.2),0 2px 6px rgba(0,0,0,.12);transition:transform .2s ease,box-shadow .2s ease}
.cc-right .cc-launcher{right:calc(24px + env(safe-area-inset-right,0px))}
.cc-left .cc-launcher{left:calc(24px + env(safe-area-inset-left,0px))}
.cc-launcher:hover{transform:scale(1.06);box-shadow:0 10px 28px rgba(0,0,0,.24)}
.cc-launcher:active{transform:scale(.96)}
.cc-launcher svg{position:absolute;transition:opacity .2s ease,transform .2s ease}
.cc-launcher .cc-i-close{opacity:0;transform:rotate(-90deg) scale(.6)}
.cc-open .cc-launcher .cc-i-chat{opacity:0;transform:rotate(90deg) scale(.6)}
.cc-open .cc-launcher .cc-i-close{opacity:1;transform:none}
.cc-dot{position:absolute;top:3px;right:3px;width:15px;height:15px;border-radius:50%;background:var(--cc-accent);border:2px solid #fff;display:none}
.cc-unread .cc-dot{display:block}

/* Greeting bubble */
.cc-greet{position:fixed;z-index:var(--cc-z);bottom:calc(32px + env(safe-area-inset-bottom,0px));max-width:min(280px,calc(100vw - 112px));display:flex;align-items:flex-start;gap:6px;padding:12px 8px 12px 14px;border-radius:14px;background:var(--cc-surface);color:var(--cc-text);box-shadow:0 6px 24px rgba(0,0,0,.18);opacity:0;transform:translateY(8px);visibility:hidden;transition:opacity .2s ease,transform .2s ease,visibility 0s linear .2s}
.cc-right .cc-greet{right:96px}
.cc-left .cc-greet{left:96px}
.cc-greet.cc-show{opacity:1;transform:none;visibility:visible;transition-delay:0s}
.cc-greet-text{text-align:left;font-size:15px}
.cc-greet-x{flex:none;width:28px;height:28px;border-radius:50%;display:flex;align-items:center;justify-content:center;color:var(--cc-muted)}
.cc-greet-x:hover{background:rgba(0,0,0,.06)}

/* Panel */
.cc-panel{position:fixed;z-index:var(--cc-z);bottom:calc(100px + env(safe-area-inset-bottom,0px));width:380px;max-width:calc(100vw - 32px);height:600px;max-height:min(80vh,calc(100vh - 124px));display:flex;flex-direction:column;overflow:hidden;border-radius:16px;background:var(--cc-surface);box-shadow:0 16px 48px rgba(0,0,0,.24),0 2px 8px rgba(0,0,0,.08);opacity:0;transform:translateY(16px);visibility:hidden;transition:opacity .2s ease,transform .2s ease,visibility 0s linear .2s}
.cc-right .cc-panel{right:24px}
.cc-left .cc-panel{left:24px}
.cc-open .cc-panel{opacity:1;transform:none;visibility:visible;transition-delay:0s}

.cc-head{flex:none;position:relative;display:flex;align-items:center;gap:10px;padding:12px 8px 12px 14px;background:var(--cc-primary);color:var(--cc-on-primary)}
.cc-head-text{flex:1;min-width:0}
.cc-title{margin:0;font-size:16px;font-weight:700;line-height:1.2}
.cc-sub{margin:2px 0 0;font-size:13px;line-height:1.2;opacity:.9}
.cc-icon-btn{flex:none;width:40px;height:40px;border-radius:50%;display:flex;align-items:center;justify-content:center;color:inherit}
.cc-head .cc-icon-btn:hover{background:rgba(255,255,255,.16)}
.cc-head :focus-visible{outline-color:var(--cc-on-primary)}

.cc-avatar{flex:none;width:32px;height:32px;border-radius:50%;object-fit:cover;background:var(--cc-surface);display:flex;align-items:center;justify-content:center;font-weight:700;font-size:15px;color:var(--cc-primary);border:1px solid rgba(0,0,0,.08)}
.cc-head .cc-avatar{width:36px;height:36px}

.cc-menu{position:absolute;top:calc(100% - 4px);right:8px;z-index:2;min-width:220px;padding:6px;border-radius:12px;background:var(--cc-surface);color:var(--cc-text);box-shadow:0 10px 30px rgba(0,0,0,.2);display:none}
.cc-menu.cc-show{display:block}
.cc-menu button{display:block;width:100%;text-align:left;padding:10px 12px;border-radius:8px;font-size:15px}
.cc-menu button:hover{background:rgba(0,0,0,.06)}

.cc-body{position:relative;flex:1;min-height:0;display:flex;flex-direction:column}
.cc-scroll{flex:1;min-height:0;overflow-y:auto;overscroll-behavior:contain;padding:16px 14px 8px;scroll-behavior:smooth}
.cc-list{display:flex;flex-direction:column;gap:10px}

.cc-welcome{padding:8px 2px 4px}
.cc-welcome-text{margin:0 0 14px;font-size:16px;font-weight:600;line-height:1.4}
.cc-chips{display:flex;flex-direction:column;align-items:flex-start;gap:8px}
.cc-chip{padding:9px 14px;border-radius:999px;border:1px solid var(--cc-primary);color:var(--cc-primary);background:var(--cc-surface);font-size:15px;text-align:left}
.cc-chip:hover{background:var(--cc-primary);color:var(--cc-on-primary)}

.cc-row{display:flex;align-items:flex-end;gap:8px;max-width:100%}
.cc-row-user{justify-content:flex-end}
.cc-msg{position:relative;max-width:82%;padding:9px 13px;border-radius:16px;overflow-wrap:anywhere}
.cc-row-user .cc-msg{background:var(--cc-primary);color:var(--cc-on-primary);border-bottom-right-radius:4px;white-space:pre-wrap}
.cc-row-bot .cc-msg{background:rgba(0,0,0,.055);color:var(--cc-text);border-bottom-left-radius:4px}
.cc-msg p{margin:0 0 .6em}
.cc-msg p:last-child,.cc-msg ul:last-child,.cc-msg ol:last-child{margin-bottom:0}
.cc-msg ul,.cc-msg ol{margin:0 0 .6em;padding-left:1.3em}
.cc-msg li{margin:.15em 0}
.cc-msg code{font-family:ui-monospace,Menlo,Consolas,monospace;font-size:.9em;background:rgba(0,0,0,.07);padding:1px 4px;border-radius:4px}
.cc-time{display:block;margin-top:3px;font-size:11px;color:var(--cc-muted);opacity:0;transition:opacity .15s}
.cc-row-user .cc-time{text-align:right}
.cc-row:hover .cc-time,.cc-row:focus-within .cc-time{opacity:1}
.cc-col{display:flex;flex-direction:column;min-width:0;max-width:82%}
.cc-row-user .cc-col{align-items:flex-end}
.cc-col .cc-msg{max-width:100%}

.cc-typing{display:inline-flex;gap:4px;padding:4px 0}
.cc-typing span{width:7px;height:7px;border-radius:50%;background:var(--cc-muted);animation:cc-bounce 1.2s infinite ease-in-out}
.cc-typing span:nth-child(2){animation-delay:.15s}
.cc-typing span:nth-child(3){animation-delay:.3s}
@keyframes cc-bounce{0%,80%,100%{transform:translateY(0);opacity:.5}40%{transform:translateY(-4px);opacity:1}}
.cc-status{font-style:italic;color:var(--cc-muted)}
.cc-queued .cc-msg{opacity:.6}
.cc-queued-note{display:block;margin-top:3px;font-size:11px;color:var(--cc-muted);text-align:right}
.cc-error{color:var(--cc-text)}
.cc-retry{margin-top:8px;padding:6px 14px;border-radius:999px;background:var(--cc-primary);color:var(--cc-on-primary);font-size:14px;font-weight:600}

.cc-pill{position:absolute;left:50%;bottom:8px;transform:translateX(-50%);display:none;align-items:center;gap:4px;padding:6px 12px;border-radius:999px;background:var(--cc-primary);color:var(--cc-on-primary);font-size:13px;font-weight:600;box-shadow:0 4px 12px rgba(0,0,0,.2)}
.cc-pill.cc-show{display:inline-flex}

.cc-notice{flex:none;margin:0 14px 8px;padding:8px 12px;border-radius:10px;background:#FFF4E5;color:#5C3B00;font-size:14px;display:none}
.cc-notice.cc-show{display:block}

.cc-composer{flex:none;padding:8px 12px 4px;border-top:1px solid rgba(0,0,0,.08)}
.cc-input-row{display:flex;align-items:flex-end;gap:8px}
.cc-input{flex:1;min-width:0;resize:none;max-height:120px;padding:10px 12px;border:1px solid rgba(0,0,0,.25);border-radius:12px;background:var(--cc-surface);color:var(--cc-text);font:inherit;font-size:16px;line-height:1.35}
.cc-input:focus-visible{outline:2px solid var(--cc-focus);outline-offset:0;border-color:transparent}
.cc-send{flex:none;width:42px;height:42px;border-radius:50%;display:flex;align-items:center;justify-content:center;background:var(--cc-primary);color:var(--cc-on-primary)}
.cc-send:disabled{opacity:.4;cursor:default}
.cc-counter{margin:4px 2px 0;font-size:12px;color:var(--cc-muted);text-align:right;display:none}
.cc-counter.cc-show{display:block}
.cc-privacy{margin:6px 2px 0;font-size:12px;color:var(--cc-muted);display:none}
.cc-privacy.cc-show{display:block}
.cc-foot{flex:none;padding:4px 12px calc(8px + env(safe-area-inset-bottom,0px));font-size:11px;color:var(--cc-muted);text-align:center}

.cc-sheet{position:absolute;inset:0;z-index:3;display:none;flex-direction:column;gap:10px;padding:20px 16px;background:var(--cc-surface)}
.cc-sheet.cc-show{display:flex}
.cc-sheet h2{margin:0 0 4px;font-size:17px}
.cc-sheet p{margin:0 0 6px;color:var(--cc-muted);font-size:14px}
.cc-contact{display:flex;align-items:center;gap:10px;padding:12px 14px;border-radius:12px;border:1px solid rgba(0,0,0,.12);color:var(--cc-text);text-decoration:none;font-weight:600}
.cc-contact:hover{background:rgba(0,0,0,.04)}
.cc-contact svg{color:var(--cc-primary)}
.cc-sheet-close{align-self:flex-start;margin-top:6px;padding:8px 14px;border-radius:999px;border:1px solid rgba(0,0,0,.2)}

/* Phones: full screen, follows the on-screen keyboard (visualViewport) */
@media (max-width:639.98px){
  .cc-panel,.cc-right .cc-panel,.cc-left .cc-panel{left:0;right:0;top:var(--cc-vv-top,0px);bottom:auto;width:100%;max-width:none;height:var(--cc-vv-height,100vh);max-height:none;border-radius:0}
  .cc-head{padding-top:max(12px,env(safe-area-inset-top,0px))}
  .cc-open .cc-launcher{visibility:hidden}
}

@media (prefers-reduced-motion:reduce){
  *,*::before,*::after{transition:none!important;animation:none!important;scroll-behavior:auto!important}
}
`;
