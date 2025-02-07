import requests
import RPi.GPIO as GPIO
import smbus
import time
import serial

# Define some device parameters
I2C_ADDR = 0x27  # I2C device address
LCD_WIDTH = 16  # Maximum characters per line

# Define some device constants
LCD_CHR = 1  # Mode - Sending data
LCD_CMD = 0  # Mode - Sending command

LCD_LINE_1 = 0x80  # LCD RAM address for the 1st line
LCD_LINE_2 = 0xC0  # LCD RAM address for the 2nd line

LCD_BACKLIGHT = 0x08  # On
ENABLE = 0b00000100  # Enable bit

# Timing constants
E_PULSE = 0.0005
E_DELAY = 0.0005

# Button pins
RFID_BUTTON_PIN = 16
PAYMENT_BUTTON_PIN = 26

# Serial port for RFID reader
SERIAL_PORT = '/dev/ttyAMA0'
SERIAL_BAUDRATE = 9600

# Flask backend URL
FLASK_URL = 'http://0.0.0.0:5001/'  

# GPIO pins for motor control
IN1 = 24
IN2 = 23
EN = 25

# Open I2C interface
bus = smbus.SMBus(1)

# Set up GPIO for motor control
GPIO.setmode(GPIO.BCM)
GPIO.setup(IN1, GPIO.OUT)
GPIO.setup(IN2, GPIO.OUT)
GPIO.setup(EN, GPIO.OUT)

# Start PWM
pwm = GPIO.PWM(EN, 1000)  # Set frequency to 1000 Hz
pwm.start(0)  # Set initial duty cycle to 0%

def lcd_init():
    # Initialise display
    lcd_byte(0x33, LCD_CMD)  # 110011 Initialise
    lcd_byte(0x32, LCD_CMD)  # 110010 Initialise
    lcd_byte(0x06, LCD_CMD)  # 000110 Cursor move direction
    lcd_byte(0x0C, LCD_CMD)  # 001100 Display On,Cursor Off, Blink Off
    lcd_byte(0x28, LCD_CMD)  # 101000 Data length, number of lines, font size
    lcd_byte(0x01, LCD_CMD)  # 000001 Clear display
    time.sleep(E_DELAY)

def lcd_byte(bits, mode):
    # Send byte to data pins
    bits_high = mode | (bits & 0xF0) | LCD_BACKLIGHT
    bits_low = mode | ((bits << 4) & 0xF0) | LCD_BACKLIGHT

    try:
        # High bits
        bus.write_byte(I2C_ADDR, bits_high)
        lcd_toggle_enable(bits_high)

        # Low bits
        bus.write_byte(I2C_ADDR, bits_low)
        lcd_toggle_enable(bits_low)
    except IOError:
        print("Error communicating with I2C device")

def lcd_toggle_enable(bits):
    # Toggle enable
    time.sleep(E_DELAY)
    try:
        bus.write_byte(I2C_ADDR, (bits | ENABLE))
        time.sleep(E_PULSE)
        bus.write_byte(I2C_ADDR, (bits & ~ENABLE))
        time.sleep(E_DELAY)
    except IOError:
        print("Error communicating with I2C device")

def lcd_string(message, line):
    # Send string to display
    message = message.ljust(LCD_WIDTH, " ")
    lcd_byte(line, LCD_CMD)

    for i in range(LCD_WIDTH):
        lcd_byte(ord(message[i]), LCD_CHR)

def read_rfid():
    ser = serial.Serial(SERIAL_PORT, SERIAL_BAUDRATE, timeout=1)
    try:
        while True:
            if ser.in_waiting > 0:
                rfid_data = ser.readline().decode().strip()
                ser.close()
                print("RFID tag scanned:", rfid_data)
                return rfid_data
    except KeyboardInterrupt:
        ser.close()
        return None

def rotate_motor(uid):
    print("Starting motor...")
    GPIO.output(IN1, GPIO.LOW)
    GPIO.output(IN2, GPIO.HIGH)
    pwm.ChangeDutyCycle(100)  # Set duty cycle to 100% (maximum speed)
    time.sleep(5)  # Run the motor for 15 seconds
    pwm.ChangeDutyCycle(0)  # Stop the motor
    print("Motor stopped.")

    try:
        # Fetch the name of the user associated with the user ID (uid)
        user_response = requests.get(f"{FLASK_URL}/get_user_name/{uid}")
        user_data = user_response.json()
        user_name = user_data['name']
        
        # Fetch the last added product
        last_product_response = requests.get(f"{FLASK_URL}/get_products")
        last_product = last_product_response.json()[-1]  # Assuming the last product is the one just added

        print("User Name:", user_name)
        print("Amount Paid:", last_product['price'])
        print("Product ID:", last_product['product_id'])

        # Send request to Flask backend to add transaction
        response = requests.post(f"{FLASK_URL}/add_transaction", json={
            'user_name': user_name,
            'amount_paid': last_product['price'],
            'product_id': last_product['product_id']
        })

        if response.status_code == 200:
            print("Payment details stored in the database.")
        else:
            print("Failed to store payment details in the database.")

        # Delete the last added product
        delete_product(last_product['product_id'])

    except Exception as e:
        print("Error:", e)


def delete_product(product_id):
    try:
        response = requests.post(f"{FLASK_URL}/delete_product", json={'product_id': product_id})
        if response.status_code == 200:
            print("Product deleted successfully.")
        else:
            print("Failed to delete product.")
    except Exception as e:
        print("Error:", e)


def main():
    # Main program block
    try:
        # Initialize display
        lcd_init()
        GPIO.setup(RFID_BUTTON_PIN, GPIO.IN, pull_up_down=GPIO.PUD_UP)
        GPIO.setup(PAYMENT_BUTTON_PIN, GPIO.IN, pull_up_down=GPIO.PUD_UP)

        while True:
            # Send initial message
            lcd_string("Scan for RFID", LCD_LINE_1)
            time.sleep(2)

            # Check for RFID button press
            while GPIO.input(RFID_BUTTON_PIN) == GPIO.HIGH:
                time.sleep(0.1)  # Wait for button press

            # Button pressed, clear display
            lcd_byte(0x01, LCD_CMD)
            # Display scanning message
            lcd_string("Scanning for RFID", LCD_LINE_1)

            # Read RFID tag
            uid = read_rfid()
            if uid is not None:
                # Send RFID data to Flask backend for validation
                response = requests.post(f"{FLASK_URL}/validate_rfid", json={'rfid': uid})
                validation_result = response.json()

                if validation_result['valid']:
                    # Clear display
                    lcd_byte(0x01, LCD_CMD)
                    # Display welcome message
                    lcd_string(f"Welcome {validation_result['name']}", LCD_LINE_1)
                    time.sleep(2)

                    # Clear display
                    lcd_byte(0x01, LCD_CMD)
                    # Fetch and display product information
                    products_response = requests.get(f"{FLASK_URL}/get_products")
                    products = products_response.json()
                    num_products = len(products)
                    # Loop to continuously display product information
                    while True:
                        # Check for payment button press to verify payment
                        if GPIO.input(PAYMENT_BUTTON_PIN) == GPIO.LOW:
                            print('payment button pressed')
                            lcd_byte(0x01, LCD_CMD)  # Clear display
                            # Send request to Flask app to check payment status
                            payment_response = requests.get('http://0.0.0.0:5001/check_flag')
                            payment_status = payment_response.json().get('flag')
                            if payment_status:
                                lcd_string("Payment success", LCD_LINE_1)
                                # Rotate motor if payment successful
                                rotate_motor(uid)  # Pass the actual user ID here

                            else:
                                lcd_string("Payment failed", LCD_LINE_1)
                            time.sleep(2)
                            break  # Exit the loop after displaying payment status

                        # Fetch and display total number of products
                        lcd_string(f"Products: {num_products}", LCD_LINE_1)

                        # Fetch and display product prices
                        for product in products:
                            lcd_byte(0x02, LCD_CMD)
                            lcd_string(f"Price: {product['price']}", LCD_LINE_2)
                            time.sleep(0.5)

                        # Display "Scan QR" message
                        lcd_byte(0x01, LCD_CMD)  # Clear display
                        lcd_string("Scan QR", LCD_LINE_1)
                        time.sleep(2)

                else:
                    print('RFID is not valid')
            else:
                print('RFID not scanned')

    except KeyboardInterrupt:
        pass
    finally:
        GPIO.cleanup()
        lcd_byte(0x01, LCD_CMD)  # Clear display

if __name__ == '__main__':
    main()
