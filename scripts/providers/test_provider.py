from configparser import ConfigParser
import providers.trakt_provider as trakt

config = ConfigParser()
config.read("paths.txt")

trakt.get_metadata("Ax Men", config)
