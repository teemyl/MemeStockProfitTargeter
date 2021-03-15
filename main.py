import os
import requests
import sqlite3
import sys
import getopt
import json
import datetime
from tabulate import tabulate

import settings
from const import CONSTANTS

class OERApi:
  app_id = None
  base_url = None

  def __init__(self):
    # Get app_id from .env file
    self.app_id = os.getenv('OPEN_EXCHANGE_RATES_APP_ID')
    self.base_url = CONSTANTS.OER_API_BASE_URL

  def _get(self, url):
    res = requests.get(
      url,
      params = { 'app_id': self.app_id }
    )
    return res.json()
  
  def get_latest(self):
    url = self.base_url + 'latest.json'
    return self._get(url)


class ProfitTargeter:
  # Targets: id, name, base_value, target_value
  # Rates: id, date, eur, usd, gbp
  db_connection = None
  db_cursor = None
  api = None
  opts = args = None

  def __init__(self, argv):
    self.db_connection = sqlite3.connect(CONSTANTS.DB_FILENAME)
    self.db_cursor = self.db_connection.cursor()
    self.api = OERApi()

    try:
      self.opts, self.args = getopt.getopt(argv, 'hpacri', ['help, print, add, calc, reset, info'])
    except getopt.GetoptError:
      print('main.py <-h --help> <-p --print> <-a --add> <-c --calc')
      sys.exit(2)

  def __del__(self):
    if self.db_connection:
      self.db_connection.close()

  def calculate_target(self, base_value, target_rate):
    base_with_additional = \
      base_value / (1 - CONSTANTS.ADDITIONAL_WITHHOLD * 0.01) \
      if CONSTANTS.ADDITIONAL_WITHHOLD \
      else base_value

    base_with_tax = \
      base_with_additional / (1 - CONSTANTS.TAX_RATE * 0.01) \
      if CONSTANTS.TAX_RATE \
      else base_with_additional

    return base_with_tax / target_rate

  def update_rates(self):
    latest = self.api.get_latest()
    
    if 'rates' in latest:
      today = datetime.date.today()

      self.db_cursor.execute(
        'INSERT INTO rates (date, eur, usd, gbp) VALUES (?, ?, ?, ?)',
        (today, latest['rates']['EUR'], float(1), latest['rates']['GBP'])
      )
      
      self.db_connection.commit()

    else:
      return None

  def get_usd_eur_by_date(self, date):
    query = self.db_cursor.execute('SELECT eur FROM rates WHERE date=?', (date,))
    return query.fetchone()

  def create_target_table(self):
    self.db_cursor.execute('CREATE TABLE targets (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, base_value FLOAT, target_value FLOAT)')

  def print_report(self):
    q = self.db_cursor.execute('SELECT * FROM targets')
    data = q.fetchall()
    data.append(('', 'TOTAL', sum([x[2] for x in data]), sum([x[3] for x in data])))
    print(tabulate(data, headers=['id', 'Name', 'Base value (€)', 'Target value ($)']))

  def run(self):

    for opt, arg in self.opts:
      if opt in ['-h', '--help']:
        print('main.py <-h --help> <-p --print> <-a --add> name value')
        sys.exit(2)

      elif opt in ['-p', '--print']:
        self.print_report()
        sys.exit()

      elif opt in ['-c', '--calc']:
        if (not len(self.args) == 2):
          print('main.py <-c --calc> base_value target_rate')
          sys.exit(2)
        print(self.calculate_target(float(self.args[0]), float(self.args[1])))

      elif opt in ['-r', '--reset']:
        self.db_cursor.execute('DROP TABLE targets')
        self.db_connection.commit()
        self.create_target_table()

      elif opt in ['-i', '--info']:
        print('Active coefficients:')
        if CONSTANTS.TAX_RATE:
          print('TAX RATE: {:.2f}%'.format(float(CONSTANTS.TAX_RATE)))
        if CONSTANTS.ADDITIONAL_WITHHOLD:
          print('ADDITIONAL WITHHOLD: {:.2f}%'.format(float(CONSTANTS.ADDITIONAL_WITHHOLD)))
        today = datetime.date.today()
        usd_eur_today = self.get_usd_eur_by_date(today)
        if usd_eur_today:
          print('USD/EUR ({}): {:.2f}'.format(today, usd_eur_today[0]))

      elif opt in ['-a', '--add']:
        # If not enough args provided, exit with error message
        if (len(self.args) < 2):
          print('main.py <-a --add> name value')
          sys.exit(2)

        name = ' '.join(self.args[0:-1])
        base_value = float(self.args[-1])

        today = datetime.date.today()
        usd_eur = self.get_usd_eur_by_date(today)[0]
        
        if not usd_eur:
          self.update_rates()
          usd_eur = self.get_usd_eur_by_date(today)[0]
        
        target_value = self.calculate_target(base_value, usd_eur)

        self.db_cursor.execute(
          'INSERT INTO targets (name,base_value,target_value) VALUES (?,?,?)',
          (name, base_value, target_value)
        )

      self.db_connection.commit()

if __name__ == "__main__":
  gme = ProfitTargeter(sys.argv[1:])
  gme.run()