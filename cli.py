"""
CLI - Interface por Linha de Comandos
Uso: python cli.py --theme curiosidades --duration 30
"""

import argparse
import logging
import sys
import json
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s"
)
logger = logging.getLogger(__name__)


def main():
    parser = argparse.ArgumentParser(
        description="🎬 TikTok Video Generator - CLI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Exemplos:
  python cli.py --theme curiosidades --duration 30
  python cli.py --theme motivacao --duration 15 --voice pt_male --language pt
  python cli.py --theme factos --duration 60 --topic "factos sobre o universo"
  python cli.py --batch configs/batch_example.json

Temas disponíveis:
  motivacao, curiosidades, historias, factos,
  tecnologia, natureza, historia, saude

Vozes disponíveis:
  pt_female, pt_male, en_female, en_male,
  es_female, es_male, robotic
        """
    )

    parser.add_argument("--theme", default="curiosidades",
                       help="Tema do vídeo (default: curiosidades)")
    parser.add_argument("--duration", type=int, default=30, choices=[15, 30, 60],
                       help="Duração em segundos (default: 30)")
    parser.add_argument("--voice", default="pt_female",
                       help="Tipo de voz (default: pt_female)")
    parser.add_argument("--language", default="pt",
                       help="Idioma (default: pt)")
    parser.add_argument("--subtitle-style", default="tiktok",
                       choices=["tiktok", "classic", "neon", "minimal"],
                       help="Estilo das legendas (default: tiktok)")
    parser.add_argument("--topic", default=None,
                       help="Tópico específico (opcional)")
    parser.add_argument("--no-music", action="store_true",
                       help="Desativa música de fundo")
    parser.add_argument("--music-volume", type=float, default=0.15,
                       help="Volume da música (0.05-0.5, default: 0.15)")
    parser.add_argument("--batch", type=str, default=None,
                       help="Ficheiro JSON com configs para geração em lote")
    parser.add_argument("--output-dir", type=str, default=None,
                       help="Diretório de saída personalizado")

    args = parser.parse_args()

    from pipeline import VideoGenerationPipeline

    def print_progress(step, total, message, job_id):
        bar_len = 30
        filled = int(bar_len * step / total)
        bar = "█" * filled + "░" * (bar_len - filled)
        print(f"\r[{bar}] {step}/{total} {message}", end="", flush=True)
        if step == total:
            print()

    if args.batch:
        # Modo batch
        batch_file = Path(args.batch)
        if not batch_file.exists():
            print(f"❌ Ficheiro batch não encontrado: {batch_file}")
            sys.exit(1)

        with open(batch_file) as f:
            configs = json.load(f)

        print(f"🚀 Iniciando geração em lote: {len(configs)} vídeos\n")
        pipe = VideoGenerationPipeline()
        results = pipe.generate_batch(configs, progress_callback=print_progress)

        print("\n" + "="*60)
        print("📊 RESULTADO DO BATCH:")
        ok = sum(1 for r in results if r["success"])
        print(f"  ✅ Sucesso: {ok}/{len(results)}")
        for i, r in enumerate(results):
            if r["success"]:
                print(f"  [{i+1}] ✅ {r.get('video_name', 'N/A')} ({r.get('size_mb', 0):.1f} MB)")
            else:
                print(f"  [{i+1}] ❌ Erro: {r.get('error', 'Desconhecido')}")

    else:
        # Modo single
        print(f"""
╔══════════════════════════════════════════╗
║    🎬 TikTok Video Generator            ║
╚══════════════════════════════════════════╝
  Tema:     {args.theme}
  Duração:  {args.duration}s
  Voz:      {args.voice}
  Idioma:   {args.language}
  Legendas: {args.subtitle_style}
  Tópico:   {args.topic or 'Automático'}
  Música:   {'Sim' if not args.no_music else 'Não'}
""")

        pipe = VideoGenerationPipeline()
        print("🚀 Iniciando geração...\n")

        result = pipe.generate_video(
            theme=args.theme,
            duration=args.duration,
            voice_type=args.voice,
            language=args.language,
            subtitle_style=args.subtitle_style,
            topic=args.topic,
            add_music=not args.no_music,
            music_volume=args.music_volume,
            progress_callback=print_progress
        )

        print("\n" + "="*60)
        if result["success"]:
            print(f"""✅ VÍDEO GERADO COM SUCESSO!
  📁 Ficheiro: {result.get('video_name')}
  📍 Path: {result.get('video_path')}
  ⏱️  Duração: {result.get('duration_real', args.duration):.1f}s
  💾 Tamanho: {result.get('size_mb', 0):.1f} MB
  ⚡ Tempo de geração: {result.get('elapsed_seconds', 0):.1f}s
""")

            script = result.get("script", {})
            print(f"🎯 Hook: {script.get('hook', 'N/A')}")
            print(f"#️⃣  Hashtags: {' '.join(script.get('hashtags', []))}")

        else:
            print(f"❌ ERRO: {result.get('error', 'Desconhecido')}")
            print(f"📋 Log: {result.get('log_path', 'N/A')}")
            sys.exit(1)


if __name__ == "__main__":
    main()
