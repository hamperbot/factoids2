from distutils.core import setup

with open('requirements.txt') as f:
    requirements = [l.strip() for l in f]

setup(
    name='hamper-factoids2',
    version='0.1',
    packages=['hamper_factoids2'],
    author='Mike Cooper',
    author_email='mythmon@gmail.com',
    url='https://github.com/mythmon/hamper-factoids2',
    install_requires=requirements,
    package_data={'hamper-factoids2': ['requirements.txt', 'README.md', 'LICENSE']},
    entry_points={
        'hamperbot.plugins': [
            'factoids2 = hamper_factoids.factoids:Factoids',
        ],
    },
)
