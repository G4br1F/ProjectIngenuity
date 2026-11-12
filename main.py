"""Run one hardware-owning server process; no device access on import."""
import os


def main():
    import uvicorn
    uvicorn.run('ingenuity.web.server:app',host=os.getenv('HOST','0.0.0.0'),
                port=int(os.getenv('PORT','8000')),workers=1)


if __name__ == '__main__':
    main()
