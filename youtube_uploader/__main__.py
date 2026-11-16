"""CLI.

    python -m youtube_uploader auth ko                 # one-time login per channel
    python -m youtube_uploader init jobs/my_video      # create ko/en/ja folders
    python -m youtube_uploader prepare jobs/my_video [--ai]
    python -m youtube_uploader upload jobs/my_video [--dry-run] [--only ko,en]
"""

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from .config import AppConfig, load_config
from .job import META_FILE, Meta, fallback_meta, finalize, scan_job
from .uploader import QUOTA


def _cfg(args) -> AppConfig:
    return load_config(args.config)


def cmd_auth(args) -> int:
    from .auth import login, whoami, youtube_service

    cfg = _cfg(args)
    keys = list(cfg.channels) if args.channel == "all" else [args.channel]
    for key in keys:
        ch = cfg.channels.get(key)
        if not ch:
            print(f"Unknown channel '{key}'. Known: {', '.join(cfg.channels)}")
            return 1
        print(f"[{key}] Browser will open. Choose the channel for '{key}' ({ch.name or ch.language}).")
        creds = login(cfg.client_secret, ch.token_path)
        me = whoami(youtube_service(creds))
        print(f"[{key}] Logged in as: {me['title']}  (channel_id: {me['id']})")
        if ch.channel_id and ch.channel_id != me["id"]:
            print(f"[{key}] WARNING: channels.json expects {ch.channel_id}. Re-run and pick the right channel.")
        elif not ch.channel_id:
            print(f'[{key}] Tip: add "channel_id": "{me["id"]}" to channels.json so uploads are verified.')
    return 0


def cmd_init(args) -> int:
    cfg = _cfg(args)
    job = Path(args.job)
    for key in cfg.channels:
        (job / key).mkdir(parents=True, exist_ok=True)
    print(f"Created {job}/{{{','.join(cfg.channels)}}}/")
    print("Put in each folder: video.mp4, script.txt, optional thumbnail.jpg and captions .srt")
    return 0


def _selected(items, cfg: AppConfig, only):
    wanted = set(only.split(",")) if only else None
    out = []
    for it in items:
        if wanted and it.key not in wanted:
            continue
        if it.key not in cfg.channels:
            print(f"[{it.key}] skipped: no channel '{it.key}' in channels.json")
            continue
        out.append(it)
    return out


def cmd_prepare(args) -> int:
    cfg = _cfg(args)
    items = _selected(scan_job(Path(args.job)), cfg, args.only)
    for it in items:
        ch = cfg.channels[it.key]
        if it.meta_path.exists() and not args.force:
            print(f"[{it.key}] {META_FILE} exists, keeping it (use --force to regenerate)")
            continue
        script = it.read_script()
        if it.script and not script.strip():
            print(f"[{it.key}] {it.script.name} is empty. Open it, paste the script, save (Ctrl+S).")
            continue
        if not script.strip():
            files = ", ".join(p.name for p in sorted(it.folder.iterdir())) or "(empty)"
            print(f"[{it.key}] no script.txt found. Files in {it.folder}: {files}")
            continue
        if args.ai:
            from .ai_meta import generate_meta

            print(f"[{it.key}] generating metadata with Claude...")
            meta = generate_meta(script, ch.language, model=args.model)
        else:
            meta = fallback_meta(script)
        it.meta_path.write_text(
            json.dumps(meta.to_dict(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        print(f"[{it.key}] wrote {it.meta_path}  title: {meta.title}")
    print("Review/edit each meta.json, then run: upload")
    return 0


def cmd_upload(args) -> int:
    cfg = _cfg(args)
    items = _selected(scan_job(Path(args.job)), cfg, args.only)
    if not items:
        print("Nothing to upload.")
        return 1

    # Validate everything before touching the network.
    plan, problems = [], []
    for it in items:
        ch = cfg.channels[it.key]
        if it.result_path.exists() and not args.force:
            done = json.loads(it.result_path.read_text(encoding="utf-8-sig"))
            print(f"[{it.key}] already uploaded: {done.get('url')} (use --force to upload again)")
            continue
        if not it.video:
            problems.append(f"[{it.key}] no video file in {it.folder}")
            continue
        if not it.meta_path.exists():
            problems.append(f"[{it.key}] no {META_FILE}; run 'prepare' first")
            continue
        try:
            meta = Meta.from_file(it.meta_path)
            if args.publish_at:
                meta.publish_at = args.publish_at
            if args.privacy:
                meta.privacy = args.privacy
            body = finalize(meta, ch)
        except ValueError as e:
            problems.append(f"[{it.key}] {e}")
            continue
        plan.append((it, ch, body))

    for p in problems:
        print(p)
    if problems:
        print("Fix the problems above; nothing was uploaded.")
        return 1
    if not plan:
        print("Nothing left to upload.")
        return 0

    quota = 0
    for it, ch, body in plan:
        sn, st = body["snippet"], body["status"]
        size_mb = it.video.stat().st_size / 1e6
        cost = QUOTA["channels.list"] + QUOTA["videos.insert"]
        cost += QUOTA["thumbnails.set"] if it.thumbnail else 0
        cost += QUOTA["captions.insert"] * len(it.captions)
        quota += cost
        when = f" at {st['publishAt']}" if "publishAt" in st else ""
        print(f"[{it.key}] -> {ch.name or ch.key}: {it.video.name} ({size_mb:.0f} MB)")
        print(f"     title: {sn['title']}")
        print(f"     {st['privacyStatus']}{when}, tags: {len(sn['tags'])}, "
              f"thumbnail: {'yes' if it.thumbnail else 'no'}, captions: {len(it.captions)}, "
              f"~{cost} quota")
    print(f"Total ~{quota} quota units (default daily quota: 10,000 per Google Cloud project)")

    if args.dry_run:
        print("Dry run: nothing uploaded.")
        return 0

    from .auth import load_or_login, whoami, youtube_service
    from .uploader import insert_caption, set_thumbnail, upload_video

    failed = 0
    for it, ch, body in plan:
        print(f"[{it.key}] uploading...")
        try:
            service = youtube_service(load_or_login(cfg.client_secret, ch.token_path, it.key))
            me = whoami(service)
            if ch.channel_id and me["id"] != ch.channel_id:
                raise RuntimeError(
                    f"token belongs to '{me['title']}' ({me['id']}), expected {ch.channel_id}. "
                    f"Re-run: python -m youtube_uploader auth {it.key}"
                )
            video_id = upload_video(service, it.video, body)
            url = f"https://youtu.be/{video_id}"
            result = {
                "video_id": video_id,
                "url": url,
                "channel": me,
                "uploaded_at": datetime.now(timezone.utc).isoformat(),
                "title": body["snippet"]["title"],
            }
            # Write the result first so a later failure never causes a duplicate upload.
            it.result_path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n",
                                      encoding="utf-8")
            print(f"[{it.key}] uploaded: {url}")

            if it.thumbnail:
                try:
                    set_thumbnail(service, video_id, it.thumbnail)
                    print(f"[{it.key}] thumbnail set")
                except Exception as e:  # channel may not be verified for custom thumbnails
                    print(f"[{it.key}] thumbnail failed: {e}")
            for cap in it.captions:
                try:
                    insert_caption(service, video_id, cap, ch.language)
                    print(f"[{it.key}] captions uploaded: {cap.name}")
                except Exception as e:
                    print(f"[{it.key}] captions failed ({cap.name}): {e}")
        except Exception as e:
            failed += 1
            print(f"[{it.key}] FAILED: {e}")

    print(f"Done: {len(plan) - failed} uploaded, {failed} failed.")
    return 1 if failed else 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="youtube_uploader",
                                description="Upload one video to per-language YouTube channels.")
    p.add_argument("--config", default="channels.json", help="path to channels.json")
    sub = p.add_subparsers(dest="cmd", required=True)

    a = sub.add_parser("auth", help="log in to a channel and save its token")
    a.add_argument("channel", help="channel key from channels.json, or 'all'")
    a.set_defaults(func=cmd_auth)

    i = sub.add_parser("init", help="create a job folder with one subfolder per channel")
    i.add_argument("job")
    i.set_defaults(func=cmd_init)

    pr = sub.add_parser("prepare", help="write meta.json (title/description/tags) per language")
    pr.add_argument("job")
    pr.add_argument("--ai", action="store_true", help="write metadata from the script with Claude")
    pr.add_argument("--model", default=None, help="Claude model for --ai")
    pr.add_argument("--only", help="comma-separated channel keys, e.g. en,ja")
    pr.add_argument("--force", action="store_true", help="overwrite existing meta.json")
    pr.set_defaults(func=cmd_prepare)

    u = sub.add_parser("upload", help="upload every language folder to its channel")
    u.add_argument("job")
    u.add_argument("--only", help="comma-separated channel keys, e.g. en,ja")
    u.add_argument("--dry-run", action="store_true", help="validate and show the plan only")
    u.add_argument("--publish-at", help="schedule, ISO 8601 with timezone (2026-11-20T18:00:00+09:00)")
    u.add_argument("--privacy", choices=["private", "unlisted", "public"])
    u.add_argument("--force", action="store_true", help="upload even if upload_result.json exists")
    u.set_defaults(func=cmd_upload)
    return p


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    if getattr(args, "model", "unset") is None:
        from .ai_meta import DEFAULT_MODEL
        args.model = DEFAULT_MODEL
    try:
        return args.func(args)
    except (FileNotFoundError, ValueError, RuntimeError) as e:
        print(f"Error: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
