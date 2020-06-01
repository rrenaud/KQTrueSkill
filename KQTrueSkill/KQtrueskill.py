import filecmp
import datetime

from trueskill import *
import csv


class KQTrueSkill:
    datetime_format: str = "%Y-%m-%dT%H:%M:%S%z"

    def __init__(self):
        self.matches: [] = []
        self.playerscenes = {}
        self.playerteams = {}
        self.playerratings = {}
        self.playertournaments = {}  # playertournaments[playername] = {"BB4","KQ30",...}
        self.playergames = {}
        self.tournaments = []
        self.tournamentdates = {}  # source data only ties matches directly to a date.
        self.teams = {}  # [tournament][team name] = {p1, p2, p3...}
        self.output_file_name: str = '2019PlayerSkill.csv'
        self.process_approved_datasets()

    # ingest the known good datasets automatically
    def process_approved_datasets(self):
        self.ingest_dataset('datasets/2019 KQ - 2019 Players.csv', 'datasets/2019 KQ - 2019 game results.csv')
        self.ingest_dataset('datasets/2018 KQ - GDC3 Players.csv', 'datasets/2018 KQ - GDC3 game results.csv')
        self.ingest_dataset('datasets/2018 KQ - BB3 Players.csv' , 'datasets/2018 KQ - BB3 matches.csv')
        self.ingest_dataset('datasets/2018 KQ - HH1 Players.csv', 'datasets/2018 KQ - HH1 game results.csv')
        # run trueskill on the matches
        self.calculate_trueskills()

    def ingest_dataset(self, playerfile: str, matchfile: str):
        # must ingest players first
        # reports new players found in this file
        self.ingest_players_from_file(playerfile)

        # expect Exceptions if your team names don't match
        self.ingest_matches_from_file(matchfile)

        # ensure matches will always process in historical order
        self.matches = sorted(self.matches, key=lambda match: match["time"])

    # wipe old ratings objects and recalculate trueskill, compare new result with old ratings
    def calculate_trueskills(self):
        # save old ratings for later comparison
        old_playerratings = self.playerratings

        # make clean ratings objects
        self.playerratings = {}
        for player in self.playerteams.keys():
            self.playerratings[player] = Rating()

        # calculate complete history
        current_tournament: str = ''
        for m in self.matches:
            t1ratings = []
            t2ratings = []
            tournament: str = m['tournament']
            team1name: str = m['team1name']
            team2name: str = m['team2name']
            team1wins: int = m['team1wins']
            team2wins: int = m['team2wins']

            if current_tournament != tournament:
                current_tournament = tournament
                print(f"processing {tournament}")

            # Trueskill wants arrays of ratings objects for each player
            # Order doesn't matter to trueskill, but it does matter to us, so preserve order as found in
            # the teams collection
            for player in self.teams[tournament][team1name]:
                t1ratings.append(self.playerratings[player])
                self.playergames[player] += team1wins + team2wins  # update player games count
            for player in self.teams[tournament][team2name]:
                t2ratings.append(self.playerratings[player])
                self.playergames[player] += team1wins + team2wins  # update player games count

            # update ratings for each game win
            for x in range(team1wins):
                t1ratings, t2ratings = rate([t1ratings, t2ratings], ranks=[0, 1])

            for x in range(team2wins):
                t1ratings, t2ratings = rate([t1ratings, t2ratings], ranks=[1, 0])

            # now put the ratings back into the main dict
            for i in range(5):
                self.playerratings[self.teams[tournament][team1name][i]] = t1ratings[i]
            for i in range(5):
                self.playerratings[self.teams[tournament][team2name][i]] = t2ratings[i]

        # log diifferences in new and old ratings
        self.compare_ratings(old_playerratings, self.playerratings)

    def compare_ratings(self, old_playerratings, playerratings):
        new_players = []
        removed_players = []
        shared_player_deltas = {}

        for p in old_playerratings.keys():
            if p in playerratings.keys():
                shared_player_deltas[
                    p] = f"mu: {playerratings[p].mu - old_playerratings[p].mu}, s: {playerratings[p].sigma - old_playerratings[p].sigma}"
            else:
                removed_players.append(p)

        for p in playerratings.keys():
            if p not in old_playerratings.keys():
                new_players.append(p)

        print(f"New Players: {new_players}")
        print(f"Removed players: {removed_players}")
        print(f"Changed players: {shared_player_deltas}")

    def ingest_players_from_file(self, filename: str):
        with open(filename) as csv_file:
            csv_reader = csv.reader(csv_file, delimiter=',')
            line_count = 0
            for row in csv_reader:
                if line_count == 0:
                    print(f'Player List Column names are {", ".join(row)}')
                    line_count += 1
                else:
                    line_count += 1
                    # print(line_count)
                    tournament = row[0]
                    playerteam = row[1]
                    playername = row[2]
                    playerscene = row[3]
                    self.add_player(playername, playerscene, playerteam, tournament)
            print(f'Processed {line_count} players from {filename}.')
            # print(f'Player Scenes: {self.playerscenes}')
            # print(f'****TEAMS: {self.teams}')

    def add_player(self, playername, playerscene, playerteam, tournament):
        if tournament not in self.tournaments:
            self.tournaments.append(tournament)
            self.teams[tournament] = {}

        self.playerscenes[playername] = playerscene

        if playerteam in self.teams[tournament].keys():
            self.teams[tournament][playerteam].append(playername)
        else:
            self.teams[tournament][playerteam] = [playername]

        if playername in self.playerteams.keys():
            self.playerteams[playername].append(playerteam + '/' + tournament)
        else:
            self.playerteams[playername] = [playerteam + '/' + tournament]

        if playername in self.playertournaments.keys():
            self.playertournaments[playername].append(tournament)
        else:
            self.playertournaments[playername] = [tournament]

        self.playergames[playername] = 0

    # side effect: updates tournament dates with dates found here
    def ingest_matches_from_file(self, filename: str):
        with open(filename) as csv_file:
            csv_reader = csv.reader(csv_file, delimiter=',')
            line_count = 0
            for row in csv_reader:
                if line_count == 0:
                    # print(f' Game Results Column names are {", ".join(row)}')
                    line_count += 1
                else:
                    # print(f'\t{row[0]}, {row[1]}, {row[2]}, {row[3]}, {row[4]}, {row[5]}, {row[6]}.')
                    tournament = row[0]
                    bracket = row[1]
                    team1name = row[2]
                    team2name = row[3]
                    team1wins = int(row[4])
                    team2wins = int(row[5])
                    time = datetime.datetime.strptime(row[6], self.datetime_format)

                    # we should not be adding any new members to our tourney/team lists here
                    if tournament not in self.tournaments:
                        raise Exception(
                            f" {tournament} not found in self.tournaments. tournaments found = {self.tournaments}")
                    if team1name not in self.teams[tournament].keys():
                        raise Exception(
                            f"{team1name} not found in teams[{tournament}]. teams found = {self.teams[tournament].keys()}")
                    if team2name not in self.teams[tournament].keys():
                        raise Exception(
                            f"{team2name} not found in teams[{tournament}]. teams found = {self.teams[tournament].keys()}")

                    # track the date for this tournament, if not already tracked
                    if tournament not in self.tournamentdates.keys():
                        self.tournamentdates[tournament] = time.date()

                    self.matches.append(
                        {"tournament": tournament,
                         "bracket": bracket,
                         "team1name": team1name,
                         "team2name": team2name,
                         "team1wins": team1wins,
                         "team2wins": team2wins,
                         "time": time,
                         })
                    line_count += 1
        print(f"Processed {line_count - 1} matches, now tracking {len(self.matches)} matches.")

    def write_player_ratings(self, filename: str = None):
        if filename is None:
            filename = self.output_file_name
        with open(filename, mode='w') as playerskillfile:
            playerskill_writer = csv.writer(playerskillfile, delimiter=',', quotechar='"', quoting=csv.QUOTE_MINIMAL)
            playerskill_writer.writerow(
                ['Player Name', 'scene', 'mu', 'sigma', 'trueskill', 'tourneys', 'games', 'teams'])
            for player in self.playerratings.keys():
                row = [player, self.playerscenes[player], self.playerratings[player].mu,
                       self.playerratings[player].sigma,
                       self.playerratings[player].mu - 2 * self.playerratings[player].sigma,
                       len(self.playertournaments[player]),
                       self.playergames[player]]
                for team in self.playerteams[player]:
                    row.append(team)
                playerskill_writer.writerow(row)

    def get_player_scene_list(self):
        playerlist = []

        for playername in self.playerteams.keys():
            playerlist.append(f"{playername} / {self.playerscenes[playername]}")

        return playerlist


def main():
    history: KQTrueSkill = KQTrueSkill()

    # print your player ratings
    history.write_player_ratings()

    print(f'Player Ratings: {history.playerratings}')

    # test whether processing changed values
    if filecmp.cmp("2019PlayerSkill.old.csv", "2019PlayerSkill.csv"):
        print("Files are same")
    else:
        print("Files are different")


if __name__ == '__main__':
    main()
