#coding: utf-8 
from time import strftime, localtime 
from datetime import timedelta, date 
import calendar 
  
 
def date_delta(n=0): 
    ''''' 
    往前或往后n天的日期是什么
    if n>=0,date is larger than today 
    if n<0,date is less than today 
    date format = "YYYY-MM-DD" 
    ''' 
    if (n<0): 
        n = abs(n) 
        return date.today()-timedelta(days=n) 
    else: 
        return date.today()+timedelta(days=n) 
  
def days_of_month(year, mon): 
    ''''' 
    某一个月有多少天
    get days of month 
    ''' 
    return calendar.monthrange(year, mon)[1] 
  

def test():
    print('day of day')
    for i in range(-10, 10):
        print(date_delta(i))

    for i in range(1, 10):
        print(days_of_month(2018, i))
 
if __name__ == "__main__":
    test()






